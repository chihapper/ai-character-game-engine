#include "NpcAgent.h"

#include "AIController.h"
#include "Animation/AnimSequence.h"
#include "Navigation/PathFollowingComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "FerryRegions.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Animation/PoseAsset.h"
#include "Components/AudioComponent.h"
#include "MindClient.h"
#include "NpcFaceAnimInstance.h"
#include "Sound/SoundWaveProcedural.h"
#include "TimerManager.h"
#include "UObject/ConstructorHelpers.h"

TArray<ANpcAgent*> ANpcAgent::All;

ANpcAgent::ANpcAgent()
{
    PrimaryActorTick.bCanEverTick = true;
    GetCapsuleComponent()->SetCapsuleSize(30.f, 90.f);
    GetCharacterMovement()->MaxWalkSpeed = 160.f;   // a tavern is not a racetrack
    GetCharacterMovement()->bOrientRotationToMovement = true;   // bodies face where they walk
    GetCharacterMovement()->RotationRate = FRotator(0.f, 240.f, 0.f);
    GetCharacterMovement()->SetAvoidanceEnabled(true);           // patrons don't merge shoulders

    // an AI controller so chosen destinations PATH around furniture instead of shoving into it
    AIControllerClass = AAIController::StaticClass();
    AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;

    // PLACEHOLDER body until the MetaHumans arrive: a visible capsule, like the Unity
    // gray-box began — the mind is what's under test first
    static ConstructorHelpers::FObjectFinder<UStaticMesh> CapsuleMesh(
        TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    UStaticMeshComponent* Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
    Body->SetupAttachment(RootComponent);
    if (CapsuleMesh.Succeeded())
    {
        Body->SetStaticMesh(CapsuleMesh.Object);
        Body->SetRelativeScale3D(FVector(0.55f, 0.55f, 1.7f));
        Body->SetRelativeLocation(FVector(0.f, 0.f, -5.f));
    }
    Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    PlaceholderBody = Body;
}

void ANpcAgent::AttachMetaHumanBody(UClass* BodyClass)
{
    if (!BodyClass || BodyActor) return;
    FActorSpawnParameters Params;
    Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    Params.Owner = this;
    BodyActor = GetWorld()->SpawnActor<AActor>(BodyClass, GetActorLocation(), GetActorRotation(), Params);
    if (!BodyActor)
    {
        UE_LOG(LogTemp, Warning, TEXT("NpcAgent %s: body class failed to spawn"), *Slug);
        return;
    }
    BodyActor->SetActorEnableCollision(false);   // the capsule owns movement and blocking
    BodyActor->AttachToComponent(GetCapsuleComponent(), FAttachmentTransformRules::SnapToTargetNotIncludingScale);
    // MetaHuman BPs face +Y at yaw 0; the capsule's forward is +X. Feet go a half-height down.
    BodyActor->SetActorRelativeRotation(FRotator(0.f, -90.f, 0.f));
    BodyActor->SetActorRelativeLocation(FVector(0.f, 0.f, -GetCapsuleComponent()->GetScaledCapsuleHalfHeight()));
    if (PlaceholderBody)
    {
        PlaceholderBody->SetVisibility(false, true);
    }

    // life in the limbs: the Core Data locomotion loops, single-node — no AnimBP authoring.
    // The game skeleton lists the plugin skeleton as compatible (unreal/anim_compat.py).
    TArray<USkeletalMeshComponent*> Meshes;
    BodyActor->GetComponents(Meshes);
    for (USkeletalMeshComponent* M : Meshes)
    {
        if (M->GetName() == TEXT("Body")) { BodyMesh = M; }
        if (M->GetName() == TEXT("Face")) { FaceMesh = M; }
    }
    if (!BodyMesh && Meshes.Num() > 0) BodyMesh = Meshes[0];
    IdleAnim = LoadObject<UAnimSequence>(nullptr, TEXT("/MetaHumanCharacter/Optional/Animation/UEFNAnimPreset/Locomotion/AS_MH_Neutral_Stand_Idle_Loop.AS_MH_Neutral_Stand_Idle_Loop"));
    WalkAnim = LoadObject<UAnimSequence>(nullptr, TEXT("/MetaHumanCharacter/Optional/Animation/UEFNAnimPreset/Locomotion/AS_MH_Neutral_Walk_Loop_F.AS_MH_Neutral_Walk_Loop_F"));
    if (!IdleAltPath.IsEmpty())
    {
        IdleAltAnim = LoadObject<UAnimSequence>(nullptr, *IdleAltPath);
    }
    // retargeted Mixamo one-shots: small human moments between beats
    for (const TCHAR* G : { TEXT("/Game/Cast/Anims/MH/MHG_Thinking.MHG_Thinking"),
                            TEXT("/Game/Cast/Anims/MH/MHG_NeckStretching.MHG_NeckStretching"),
                            TEXT("/Game/Cast/Anims/MH/MHG_Shrugging.MHG_Shrugging"),
                            TEXT("/Game/Cast/Anims/MH/MHG_Yawn.MHG_Yawn") })
    {
        if (UAnimSequence* A = LoadObject<UAnimSequence>(nullptr, G))
        {
            Gestures.Add(A);
        }
    }
    CurrentIdle = IdleAnim;
    if (BodyMesh && IdleAnim)
    {
        BodyMesh->PlayAnimation(IdleAnim, true);
        bAnimWalking = false;
    }
    // the face gets its own loop — blinks and a resting expression that fits the character
    if (!FaceLoopPath.IsEmpty())
    {
        FaceLoop = LoadObject<UAnimSequence>(nullptr, *FaceLoopPath);
    }
    if (FaceMesh && FaceLoop)
    {
        FaceMesh->PlayAnimation(FaceLoop, true);
    }
    // reaction faces: the ENGINE decides which expression a beat surfaces (expression-relevance);
    // clip variants differ per set/sex, so try candidates and keep whichever exists
    const FString Ex = TEXT("/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Expression_Loops/");
    auto TryLoad = [](std::initializer_list<FString> Paths) -> UAnimSequence*
    {
        for (const FString& P : Paths)
        {
            if (UAnimSequence* A = LoadObject<UAnimSequence>(nullptr, *P)) return A;
        }
        return nullptr;
    };
    const FString S = FaceSex.IsEmpty() ? TEXT("f") : FaceSex;
    FaceReactions.Add(TEXT("happy"), TryLoad({
        Ex + FString::Printf(TEXT("Happy%s/mhc_mh002_fmn_f_facialloop_happy_%s_s001.mhc_mh002_fmn_f_facialloop_happy_%s_s001"), S == TEXT("f") ? TEXT("A") : TEXT("B"), *S, *S),
        Ex + FString::Printf(TEXT("Happy%s/ue_mh002_fmn_f_facialloop_happy_%s_s001.ue_mh002_fmn_f_facialloop_happy_%s_s001"), S == TEXT("f") ? TEXT("A") : TEXT("B"), *S, *S) }));
    for (const TCHAR* Emo : { TEXT("sad"), TEXT("angry"), TEXT("fear"), TEXT("surprise") })
    {
        TArray<UAnimSequence*> Found;
        for (const TCHAR* SetTag : { TEXT("A"), TEXT("B") })
        {
            const FString EmoCap = FString(Emo) == TEXT("angry") ? TEXT("Anger") : FString(FString::Chr(FChar::ToUpper(Emo[0])) + FString(Emo + 1));
            const FString P = Ex + FString::Printf(TEXT("%s%s/mhc_mh002_fmn_f_facialloop_%s_%s_s001.mhc_mh002_fmn_f_facialloop_%s_%s_s001"), *EmoCap, SetTag, Emo, *S, Emo, *S);
            if (UAnimSequence* A = LoadObject<UAnimSequence>(nullptr, *P)) { Found.Add(A); break; }
        }
        if (Found.Num()) FaceReactions.Add(Emo, Found[0]);
    }
    // occasional idle change-ups so nobody stands like a museum piece
    GetWorldTimerManager().SetTimer(IdleVarietyTimer, this, &ANpcAgent::VaryIdle,
                                    FMath::FRandRange(16.f, 30.f), true, FMath::FRandRange(6.f, 18.f));
}

void ANpcAgent::FlinchAt(const FVector& Where)
{
    FVector Dir = Where - GetActorLocation();
    Dir.Z = 0.f;
    if (!Dir.IsNearlyZero() && !bWalking)
    {
        SetActorRotation(Dir.Rotation());
    }
    if (FaceMesh && !bFaceTrackPlaying)   // never let a startle stomp live lip-sync
    {
        if (UAnimSequence** Startle = FaceReactions.Find(TEXT("surprise")))
        {
            FaceMesh->PlayAnimation(*Startle, true);
            GetWorldTimerManager().SetTimer(FaceReturnTimer,
                FTimerDelegate::CreateWeakLambda(this, [this]()
                {
                    if (FaceMesh && FaceLoop) { FaceMesh->PlayAnimation(FaceLoop, true); }
                }), 3.5f, false);
        }
    }
}

void ANpcAgent::BeginListening(const FVector& From)
{
    FVector Dir = From - GetActorLocation();
    Dir.Z = 0.f;
    if (!Dir.IsNearlyZero() && !bWalking)
    {
        SetActorRotation(Dir.Rotation());
    }
    // a "considering you" body beat during the reply latency — keeps her alive while the mind
    // works. NO startle expression: being spoken to isn't alarming; the neutral face stays.
    if (BodyMesh && !bAnimWalking)
    {
        if (UAnimSequence* Think = LoadObject<UAnimSequence>(nullptr,
            TEXT("/Game/Cast/Anims/MH/MHG_Thinking.MHG_Thinking")))
        {
            BodyMesh->PlayAnimation(Think, true);
        }
    }
}

void ANpcAgent::PlayTalkGesture(float Seconds, bool bIncludeFace)
{
    // face: a syllabic jaw/lip loop (authored curves, same rig-logic path as the expression
    // loops) for the duration of the voice clip, then settle back to the neutral loop
    if (FaceMesh && bIncludeFace)
    {
        if (UAnimSequence* FaceTalk = LoadObject<UAnimSequence>(nullptr,
            TEXT("/Game/Cast/Anims/MH/FaceTalk.FaceTalk")))
        {
            FaceMesh->PlayAnimation(FaceTalk, true);
            GetWorldTimerManager().SetTimer(TalkFaceTimer,
                FTimerDelegate::CreateWeakLambda(this, [this]()
                {
                    if (FaceMesh && FaceLoop) { FaceMesh->PlayAnimation(FaceLoop, true); }
                }), FMath::Max(1.f, Seconds), false);
        }
    }

    if (!BodyMesh || bAnimWalking) return;
    UAnimSequence* Talk = LoadObject<UAnimSequence>(nullptr,
        TEXT("/Game/Cast/Anims/MH/MHG_Talking.MHG_Talking"));
    if (!Talk) return;
    BodyMesh->PlayAnimation(Talk, true);
    GetWorldTimerManager().SetTimer(GestureReturnTimer,
        FTimerDelegate::CreateWeakLambda(this, [this]()
        {
            if (!bAnimWalking && BodyMesh && CurrentIdle) { BodyMesh->PlayAnimation(CurrentIdle, true); }
        }), FMath::Max(1.f, Seconds), false);
}

bool ANpcAgent::PlayFaceTrack(TSharedPtr<FJsonObject> AnimJson)
{
    if (!FaceMesh || !AnimJson.IsValid()) return false;
    const TArray<TSharedPtr<FJsonValue>>* NamesJson = nullptr;
    const TArray<TSharedPtr<FJsonValue>>* FramesJson = nullptr;
    if (!AnimJson->TryGetArrayField(TEXT("blendshape_names"), NamesJson) ||
        !AnimJson->TryGetArrayField(TEXT("frames"), FramesJson) ||
        NamesJson->Num() == 0 || FramesJson->Num() == 0)
    {
        return false;
    }

    FaceTrackNames.Reset();
    BlinkIdxL = BlinkIdxR = EyeLookIdxL = EyeLookIdxR = -1;
    for (const TSharedPtr<FJsonValue>& V : *NamesJson)
    {
        const FString Nm = V->AsString();
        const int32 Idx = FaceTrackNames.Add(FName(*Nm));
        if (Nm == TEXT("EyeBlinkLeft")) BlinkIdxL = Idx;
        else if (Nm == TEXT("EyeBlinkRight")) BlinkIdxR = Idx;
        else if (Nm == TEXT("EyeLookOutLeft")) EyeLookIdxL = Idx;
        else if (Nm == TEXT("EyeLookOutRight")) EyeLookIdxR = Idx;
    }
    FaceLifeSeed = FMath::FRandRange(0.f, 100.f);   // so agents don't blink in lockstep
    FaceTrackFrames.Reset();
    for (const TSharedPtr<FJsonValue>& V : *FramesJson)
    {
        const TSharedPtr<FJsonObject> F = V->AsObject();
        if (!F.IsValid()) continue;
        FFaceFrame Frame;
        Frame.Time = (float)F->GetNumberField(TEXT("t"));
        for (const TSharedPtr<FJsonValue>& W : F->GetArrayField(TEXT("w")))
        {
            Frame.Weights.Add((float)W->AsNumber());
        }
        FaceTrackFrames.Add(MoveTemp(Frame));
    }
    if (FaceTrackFrames.Num() == 0) return false;

    UPoseAsset* Mapping = LoadObject<UPoseAsset>(nullptr,
        TEXT("/Game/Cast/Built/Common/Face/ARKit/PA_MetaHuman_ARKit_Mapping.PA_MetaHuman_ARKit_Mapping"));
    if (!Mapping) return false;

    GetWorldTimerManager().ClearTimer(TalkFaceTimer);   // the real track outranks FaceTalk
    FaceMesh->SetAnimInstanceClass(UNpcFaceAnimInstance::StaticClass());
    UNpcFaceAnimInstance* Inst = Cast<UNpcFaceAnimInstance>(FaceMesh->GetAnimInstance());
    if (!Inst)
    {
        if (FaceLoop) { FaceMesh->PlayAnimation(FaceLoop, true); }
        return false;
    }
    Inst->MappingAsset = Mapping;
    FaceMesh->InitAnim(true);   // re-run proxy Initialize now that the mapping is set

    FaceTrackClock = 0.f;
    FaceTrackCursor = 0;
    bFaceTrackPlaying = true;
    return true;
}

float ANpcAgent::PlayVoice(const TArray<uint8>& Pcm, int32 Rate)
{
    if (Pcm.Num() < 2 || Rate <= 0) return 0.f;
    USoundWaveProcedural* Wave = NewObject<USoundWaveProcedural>();
    Wave->SetSampleRate(Rate);
    Wave->NumChannels = 1;
    Wave->Duration = (float)(Pcm.Num() / 2) / (float)Rate;
    Wave->SoundGroup = SOUNDGROUP_Voice;
    Wave->bLooping = false;
    Wave->QueueAudio(Pcm.GetData(), Pcm.Num());

    VoiceClipDuration = Wave->Duration;
    VoicePlayTime = 0.f;
    bVoiceSlaved = false;
    if (VoiceAudio) { VoiceAudio->Stop(); VoiceAudio->DestroyComponent(); VoiceAudio = nullptr; }

    // a manually-created component so the playback-percent delegate is bound BEFORE Play() — the
    // audio device only tracks playback position when the delegate is already bound at play time.
    // That position is what the face track slaves to (see TickFaceTrack), so the mouth follows the
    // AUDIO, never a free-running game clock that a frame hitch could drift off the words.
    UAudioComponent* AC = NewObject<UAudioComponent>(this);
    AC->bAutoActivate = false;
    AC->bAutoDestroy = true;           // self-cleans when the clip finishes
    AC->bAllowSpatialization = true;
    AC->SetSound(Wave);
    AC->SetWorldLocation(GetActorLocation());
    AC->OnAudioPlaybackPercentNative.AddUObject(this, &ANpcAgent::OnVoicePlaybackPercent);
    AC->RegisterComponent();
    AC->Play();
    VoiceAudio = AC;
    return Wave->Duration;
}

void ANpcAgent::OnVoicePlaybackPercent(const UAudioComponent* Comp, const USoundWave* Wave, float Percent)
{
    if (Comp != VoiceAudio) return;   // ignore a stale prior clip's tail callbacks
    VoicePlayTime = Percent * VoiceClipDuration;
    bVoiceSlaved = true;
}

void ANpcAgent::TickFaceTrack(float DeltaSeconds)
{
    if (!bFaceTrackPlaying || !FaceMesh) return;
    // SLAVE the face to the audio's real playback position once it's reporting; until the first
    // callback lands, advance on the game clock so the opening frames aren't frozen
    if (bVoiceSlaved && VoiceAudio && VoiceAudio->IsPlaying())
    {
        FaceTrackClock = VoicePlayTime;
    }
    else
    {
        FaceTrackClock += DeltaSeconds;
    }
    const float End = FaceTrackFrames.Last().Time;
    if (FaceTrackClock > End + 0.25f)
    {
        bFaceTrackPlaying = false;   // clip over: hand the face back to the neutral loop
        if (FaceLoop) { FaceMesh->PlayAnimation(FaceLoop, true); }
        return;
    }
    while (FaceTrackCursor + 1 < FaceTrackFrames.Num() &&
           FaceTrackFrames[FaceTrackCursor + 1].Time <= FaceTrackClock)
    {
        ++FaceTrackCursor;
    }
    const FFaceFrame& A = FaceTrackFrames[FaceTrackCursor];
    const FFaceFrame* B = FaceTrackCursor + 1 < FaceTrackFrames.Num()
        ? &FaceTrackFrames[FaceTrackCursor + 1] : nullptr;
    const float Alpha = (B && B->Time > A.Time)
        ? FMath::Clamp((FaceTrackClock - A.Time) / (B->Time - A.Time), 0.f, 1.f) : 0.f;
    TArray<float> Now;
    const int32 N = FMath::Min(FaceTrackNames.Num(), A.Weights.Num());
    Now.SetNumUninitialized(N);
    for (int32 I = 0; I < N; ++I)
    {
        const float WB = (B && I < B->Weights.Num()) ? B->Weights[I] : A.Weights[I];
        Now[I] = FMath::Lerp(A.Weights[I], WB, Alpha);
    }

    // ---- keep the eyes ALIVE (A2F leaves them staring) ----------------------------------------
    const float T = FaceTrackClock + FaceLifeSeed;
    // a blink roughly every ~3.4s: a fast close-and-open (~0.14s), eased
    const float Cycle = FMath::Fmod(T, 3.4f);
    if (Cycle < 0.14f)
    {
        const float Blink = FMath::Sin(Cycle / 0.14f * PI);   // 0 -> 1 -> 0
        if (BlinkIdxL != INDEX_NONE && BlinkIdxL < N) Now[BlinkIdxL] = FMath::Max(Now[BlinkIdxL], Blink);
        if (BlinkIdxR != INDEX_NONE && BlinkIdxR < N) Now[BlinkIdxR] = FMath::Max(Now[BlinkIdxR], Blink);
    }
    // slow, small wandering gaze so the eyes don't lock dead-ahead (Perlin = smooth, non-repeating)
    const float Gaze = 0.12f * FMath::PerlinNoise1D(T * 0.35f);
    if (Gaze > 0.f && EyeLookIdxL != INDEX_NONE && EyeLookIdxL < N) Now[EyeLookIdxL] = FMath::Max(Now[EyeLookIdxL], Gaze);
    if (Gaze < 0.f && EyeLookIdxR != INDEX_NONE && EyeLookIdxR < N) Now[EyeLookIdxR] = FMath::Max(Now[EyeLookIdxR], -Gaze);

    if (UNpcFaceAnimInstance* Inst = Cast<UNpcFaceAnimInstance>(FaceMesh->GetAnimInstance()))
    {
        Inst->SetArkitWeights(FaceTrackNames, Now);
    }
}

void ANpcAgent::TestSpeakAnim(const FString& Line, const FString& Face)
{
    UMindClient* MindC = Mind();
    if (!MindC || !MindC->HasSession()) return;
    TArray<TSharedPtr<FJsonValue>> Marks;
    if (!Face.IsEmpty())
    {
        const TSharedPtr<FJsonObject> M = MakeShared<FJsonObject>();
        M->SetNumberField(TEXT("frac"), 0.0);
        M->SetStringField(TEXT("face"), Face);
        Marks.Add(MakeShared<FJsonValueObject>(M));
    }
    MindC->SpeakAnim(Slug, Line, Marks, FMindSpeakAnimReply::CreateWeakLambda(this,
        [this](const TArray<uint8>& Pcm, int32 Rate, TSharedPtr<FJsonObject> Anim)
        {
            if (Pcm.Num() < 2) return;
            const bool bFaced = PlayFaceTrack(Anim);   // arm the face BEFORE audio so it slaves from frame 1
            const float Dur = PlayVoice(Pcm, Rate);
            PlayTalkGesture(Dur, !bFaced);
            UE_LOG(LogTemp, Display, TEXT("TestSpeakAnim %s: %.1fs audio, face track: %s"),
                   *Handle, Dur, bFaced ? TEXT("A2F") : TEXT("fallback"));
        }));
}

void ANpcAgent::VaryIdle()
{
    if (bAnimWalking || !BodyMesh) return;
    const float Roll = FMath::FRand();
    if (Gestures.Num() > 0 && Roll < 0.30f)
    {
        // one-shot gesture, then settle back into the current idle
        UAnimSequence* G = Gestures[FMath::RandRange(0, Gestures.Num() - 1)];
        BodyMesh->PlayAnimation(G, false);
        GetWorldTimerManager().SetTimer(GestureReturnTimer,
            FTimerDelegate::CreateWeakLambda(this, [this]()
            {
                if (!bAnimWalking && BodyMesh && CurrentIdle)
                {
                    BodyMesh->PlayAnimation(CurrentIdle, true);
                }
            }),
            FMath::Max(0.5f, G->GetPlayLength() - 0.05f), false);
        return;
    }
    UAnimSequence* Pick = (IdleAltAnim && Roll < 0.65f) ? IdleAltAnim : IdleAnim;
    CurrentIdle = Pick;
    BodyMesh->PlayAnimation(Pick, true);
}

void ANpcAgent::BeginPlay()
{
    Super::BeginPlay();
    All.Add(this);
    // stagger first beats so four minds don't fire at once
    const float FirstBeat = FMath::FRandRange(8.f, 20.f);
    GetWorldTimerManager().SetTimer(LifeTimer, this, &ANpcAgent::TakeBeat, 30.f, true, FirstBeat);
}

void ANpcAgent::EndPlay(const EEndPlayReason::Type Reason)
{
    if (VoiceAudio)
    {
        VoiceAudio->Stop();
        VoiceAudio = nullptr;
    }
    if (BodyActor)
    {
        BodyActor->Destroy();
        BodyActor = nullptr;
    }
    All.Remove(this);
    Super::EndPlay(Reason);
}

void ANpcAgent::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    TickFaceTrack(DeltaSeconds);
    // swap idle/walk loops with actual motion, not intent — no sliding statues
    if (BodyMesh && IdleAnim && WalkAnim)
    {
        const bool bMoving = GetVelocity().SizeSquared2D() > 25.f;
        if (bMoving != bAnimWalking)
        {
            bAnimWalking = bMoving;
            BodyMesh->PlayAnimation(bAnimWalking ? WalkAnim : (CurrentIdle ? CurrentIdle : IdleAnim), true);
        }
    }
    if (bWalking)
    {
        const FVector To = WalkTarget - GetActorLocation();
        if (To.Size2D() < 60.f)
        {
            bWalking = false;
        }
        else
        {
            AddMovementInput(To.GetSafeNormal2D(), 1.f);
        }
    }
    else if (!bAnimWalking)
    {
        // people notice someone stepping close: turn to face the traveler inside 3.5m
        if (APawn* Player = GetWorld()->GetFirstPlayerController() ? GetWorld()->GetFirstPlayerController()->GetPawn() : nullptr)
        {
            FVector ToPlayer = Player->GetActorLocation() - GetActorLocation();
            ToPlayer.Z = 0.f;
            if (ToPlayer.Size2D() < 350.f && !ToPlayer.IsNearlyZero())
            {
                const FRotator Want = ToPlayer.Rotation();
                SetActorRotation(FMath::RInterpTo(GetActorRotation(), Want, DeltaSeconds, 3.5f));
            }
        }
    }
}

UMindClient* ANpcAgent::Mind() const
{
    return GetGameInstance() ? GetGameInstance()->GetSubsystem<UMindClient>() : nullptr;
}

FString ANpcAgent::ComposeSituation() const
{
    // first-person percept, earned from real space — same contract as the Unity composer
    const FString Here = FerryRegions::NameAt(GetActorLocation());
    FString Others;
    for (const ANpcAgent* O : All)
    {
        if (O == this) continue;
        const float Dist = FVector::Dist2D(GetActorLocation(), O->GetActorLocation()) / 100.f;
        Others += FString::Printf(TEXT(" %s is %s, about %.0f paces away."),
                                  *O->Handle, *FerryRegions::NameAt(O->GetActorLocation()),
                                  FMath::Max(1.f, Dist / 0.75f));
    }
    return FString::Printf(
        TEXT("You are %s, in the tavern's taproom, at %s. Your stance: %s.%s"),
        *Handle, *Here, *Stance, *Others);
}

TArray<FString> ANpcAgent::ComposeOptions() const
{
    TArray<FString> Options;
    const FString Here = FerryRegions::NameAt(GetActorLocation());
    for (const TPair<FString, FVector>& It : FerryRegions::All())
    {
        if (It.Key != Here)
        {
            Options.Add(FString::Printf(TEXT("cross to %s"), *It.Key));
        }
    }
    for (const ANpcAgent* O : All)
    {
        if (O != this)
        {
            Options.Add(FString::Printf(TEXT("watch %s"), *O->Handle));
        }
    }
    Options.Add(TEXT("stay where you are, watchful"));
    return Options;
}

void ANpcAgent::TakeBeat()
{
    UMindClient* M = Mind();
    if (bBusy || !M || !M->HasSession()) return;
    bBusy = true;

    M->Choose(Slug, ComposeSituation(), ComposeOptions(),
        FMindJsonReply::CreateWeakLambda(this, [this](TSharedPtr<FJsonObject> Json)
        {
            bBusy = false;
            if (!Json.IsValid()) return;
            FString Action, Reason, Expression, Face;
            Json->TryGetStringField(TEXT("action"), Action);
            Json->TryGetStringField(TEXT("reason"), Reason);
            Json->TryGetStringField(TEXT("expression"), Expression);
            Json->TryGetStringField(TEXT("face"), Face);
            UE_LOG(LogTemp, Display, TEXT("MINDBEAT %s -> '%s' (%s) [face: %s | %s]"),
                   *Slug, *Action, *Reason, *Face, *Expression);
            // the engine chose what surfaces on the face this beat; wear it for a while, then settle
            if (FaceMesh && !bFaceTrackPlaying && !Face.IsEmpty() && Face != TEXT("neutral"))
            {
                if (UAnimSequence** Loop = FaceReactions.Find(Face))
                {
                    FaceMesh->PlayAnimation(*Loop, true);
                    GetWorldTimerManager().SetTimer(FaceReturnTimer,
                        FTimerDelegate::CreateWeakLambda(this, [this]()
                        {
                            if (FaceMesh && FaceLoop) { FaceMesh->PlayAnimation(FaceLoop, true); }
                        }), 4.f, false);   // a passing expression, not a mask held until it turns uncanny
                }
            }
            Enact(Action, Reason);
            // the mind must KNOW the body did it
            if (!Action.IsEmpty() && !Action.StartsWith(TEXT("stay where")))
            {
                Mind()->Acted(Slug, Action, Reason);
            }
        }));
}

void ANpcAgent::Enact(const FString& Action, const FString& Reason)
{
    if (Action.StartsWith(TEXT("cross to ")))
    {
        const FString Region = Action.Mid(9);
        Stance = FString::Printf(TEXT("just arrived at %s"), *Region);
        WalkTo(FerryRegions::Anchor(Region));
    }
    else if (Action.StartsWith(TEXT("watch ")))
    {
        const FString Who = Action.Mid(6);
        Stance = FString::Printf(TEXT("watching %s"), *Who);
        for (const ANpcAgent* O : All)
        {
            if (O->Handle == Who)
            {
                FVector Dir = O->GetActorLocation() - GetActorLocation();
                Dir.Z = 0.f;
                if (!Dir.IsNearlyZero()) SetActorRotation(Dir.Rotation());
                break;
            }
        }
    }
}

void ANpcAgent::WalkTo(const FVector& Target)
{
    WalkTarget = Target;
    if (AAIController* AI = Cast<AAIController>(GetController()))
    {
        const EPathFollowingRequestResult::Type R = AI->MoveToLocation(Target, 55.f);
        if (R != EPathFollowingRequestResult::Type::Failed)
        {
            bWalking = false;   // pathing handles it; Tick's fallback steering stays out of the way
            return;
        }
    }
    bWalking = true;   // no controller / off the navmesh: fall back to straight-line steering
}
