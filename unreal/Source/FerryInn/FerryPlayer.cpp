#include "FerryPlayer.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Engine/Engine.h"
#include "FerryRegions.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "MindClient.h"
#include "NpcAgent.h"
#include "Sound/SoundWaveProcedural.h"

AFerryPlayer::AFerryPlayer()
{
    PrimaryActorTick.bCanEverTick = true;
    GetCapsuleComponent()->SetCapsuleSize(30.f, 90.f);
    GetCharacterMovement()->MaxWalkSpeed = 260.f;   // a traveler moves with purpose, not at a sprint

    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Eyes"));
    Camera->SetupAttachment(RootComponent);
    Camera->SetRelativeLocation(FVector(0.f, 0.f, 62.f));   // eye height on the capsule
    Camera->bUsePawnControlRotation = true;
}

void AFerryPlayer::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);
    Input->BindAxis(TEXT("MoveForward"), this, &AFerryPlayer::MoveForward);
    Input->BindAxis(TEXT("MoveRight"), this, &AFerryPlayer::MoveRight);
    Input->BindAxis(TEXT("Turn"), this, &APawn::AddControllerYawInput);
    Input->BindAxis(TEXT("LookUp"), this, &APawn::AddControllerPitchInput);
    Input->BindAction(TEXT("Talk"), IE_Pressed, this, &AFerryPlayer::StartTalk);
    Input->BindAction(TEXT("Talk"), IE_Released, this, &AFerryPlayer::StopTalk);
}

// ---- push-to-talk: the player's voice enters the world ---------------------------------------

void AFerryPlayer::StartTalk()
{
    if (bTalking || bLineBusy) return;
    {
        FScopeLock Lock(&CaptureLock);
        CaptureSamples.Reset();
    }
    Audio::FAudioCaptureDeviceParams Params;   // default mic
    Audio::FOnAudioCaptureFunction OnCapture =
        [this](const void* InAudio, int32 NumFrames, int32 NumChannels, int32 SampleRate, double, bool)
        {
            const float* Samples = static_cast<const float*>(InAudio);
            FScopeLock Lock(&CaptureLock);
            CaptureRate = SampleRate;
            for (int32 F = 0; F < NumFrames; ++F)
            {
                float Mono = 0.f;   // mix channels down; the mind only needs the words
                for (int32 C = 0; C < NumChannels; ++C) Mono += Samples[F * NumChannels + C];
                Mono /= FMath::Max(1, NumChannels);
                CaptureSamples.Add((int16)FMath::Clamp(Mono * 32767.f, -32768.f, 32767.f));
            }
        };
    if (AudioCapture.OpenAudioCaptureStream(Params, MoveTemp(OnCapture), 1024))
    {
        AudioCapture.StartStream();
        bTalking = true;
        if (GEngine) GEngine->AddOnScreenDebugMessage(11, 30.f, FColor::Yellow, TEXT("listening... (release V to send)"));
    }
    else if (GEngine)
    {
        GEngine->AddOnScreenDebugMessage(11, 5.f, FColor::Red, TEXT("no microphone available"));
    }
}

void AFerryPlayer::StopTalk()
{
    if (!bTalking) return;
    bTalking = false;
    AudioCapture.StopStream();
    AudioCapture.CloseStream();

    TArray<int16> Samples;
    int32 Rate;
    {
        FScopeLock Lock(&CaptureLock);
        Samples = MoveTemp(CaptureSamples);
        Rate = CaptureRate;
    }
    if (GEngine) GEngine->AddOnScreenDebugMessage(11, 0.1f, FColor::Yellow, TEXT(""));
    if (Samples.Num() < Rate / 4) return;   // sub-quarter-second: a misclick, not a sentence

    // 44-byte PCM WAV wrapper — the server's STT wants a self-describing clip
    const int32 DataBytes = Samples.Num() * 2;
    TArray<uint8> Wav;
    Wav.Reserve(44 + DataBytes);
    auto U32 = [&Wav](uint32 V) { Wav.Append(reinterpret_cast<uint8*>(&V), 4); };
    auto U16 = [&Wav](uint16 V) { Wav.Append(reinterpret_cast<uint8*>(&V), 2); };
    Wav.Append((const uint8*)"RIFF", 4); U32(36 + DataBytes); Wav.Append((const uint8*)"WAVE", 4);
    Wav.Append((const uint8*)"fmt ", 4); U32(16); U16(1); U16(1); U32(Rate); U32(Rate * 2); U16(2); U16(16);
    Wav.Append((const uint8*)"data", 4); U32(DataBytes);
    Wav.Append(reinterpret_cast<const uint8*>(Samples.GetData()), DataBytes);

    UMindClient* Mind = GetGameInstance() ? GetGameInstance()->GetSubsystem<UMindClient>() : nullptr;
    if (!Mind || !Mind->HasSession()) return;
    bLineBusy = true;
    if (GEngine) GEngine->AddOnScreenDebugMessage(12, 20.f, FColor::Cyan, TEXT("..."));
    Mind->Stt(Wav, FMindJsonReply::CreateWeakLambda(this, [this](TSharedPtr<FJsonObject> Json)
    {
        FString Line;
        if (Json.IsValid()) Json->TryGetStringField(TEXT("text"), Line);
        if (Line.TrimStartAndEnd().IsEmpty())
        {
            bLineBusy = false;
            if (GEngine) GEngine->AddOnScreenDebugMessage(12, 3.f, FColor::Cyan, TEXT("(nothing heard)"));
            return;
        }
        if (GEngine) GEngine->AddOnScreenDebugMessage(12, 8.f, FColor::Cyan,
            FString::Printf(TEXT("You: %s"), *Line));
        HandleSpokenLine(Line);
    }));
}

ANpcAgent* AFerryPlayer::NearestAgent(float MaxDist) const
{
    ANpcAgent* Best = nullptr;
    float BestDist = MaxDist;
    for (ANpcAgent* A : ANpcAgent::All)
    {
        const float D = FVector::Dist2D(GetActorLocation(), A->GetActorLocation());
        if (D < BestDist) { BestDist = D; Best = A; }
    }
    return Best;
}

void AFerryPlayer::HandleSpokenLine(const FString& Line)
{
    ANpcAgent* Who = NearestAgent(500.f);
    UMindClient* Mind = GetGameInstance() ? GetGameInstance()->GetSubsystem<UMindClient>() : nullptr;
    if (!Who || !Mind)
    {
        bLineBusy = false;
        if (GEngine) GEngine->AddOnScreenDebugMessage(13, 4.f, FColor::Silver, TEXT("(no one close enough to hear)"));
        return;
    }
    Who->BeginListening(GetActorLocation());   // turn + a "considering" beat through the reply wait
    const FString Location = FString::Printf(TEXT("%s, in the tavern's taproom"),
        *FerryRegions::NameAt(Who->GetActorLocation()));
    TArray<FString> Present;
    Present.Add(TEXT("the traveler stands right in front of you, speaking to you"));
    for (const ANpcAgent* Other : ANpcAgent::All)
    {
        if (Other == Who) continue;
        Present.Add(FString::Printf(TEXT("%s is at %s"),
            *Other->Handle, *FerryRegions::NameAt(Other->GetActorLocation())));
    }
    // Who is a UObject held across two chained network hops (~seconds). The weak lambda guards
    // `this` (the player), not the NPC — so weak-track Who too and bail if it's gone by the time
    // a reply lands, rather than dereference a dangling actor.
    const TWeakObjectPtr<ANpcAgent> WhoW(Who);
    Mind->Respond(Who->Slug, Line, Location, Present,
        TEXT("rain drums on the roof; the storm outside has the ferry grounded for the night"),
        FMindJsonReply::CreateWeakLambda(this, [this, WhoW](TSharedPtr<FJsonObject> Json)
        {
            ANpcAgent* Who = WhoW.Get();
            if (!Who) { bLineBusy = false; return; }
            FString Reply;
            if (Json.IsValid()) Json->TryGetStringField(TEXT("reply"), Reply);
            if (Reply.IsEmpty())
            {
                bLineBusy = false;
                return;
            }
            // the engine's stage machinery: what shows on the face, and where the line turns
            TArray<TSharedPtr<FJsonValue>> FaceMarks;
            const TArray<TSharedPtr<FJsonValue>>* MarksPtr = nullptr;
            if (Json->TryGetArrayField(TEXT("face_marks"), MarksPtr))
            {
                FaceMarks = *MarksPtr;
            }
            if (GEngine) GEngine->AddOnScreenDebugMessage(13, 12.f, FColor::Green,
                FString::Printf(TEXT("%s: %s"), *Who->Handle, *Reply));
            UMindClient* Mind2 = GetGameInstance() ? GetGameInstance()->GetSubsystem<UMindClient>() : nullptr;
            if (!Mind2) { bLineBusy = false; return; }
            Mind2->SpeakAnim(Who->Slug, Reply, FaceMarks, FMindSpeakAnimReply::CreateWeakLambda(this,
                [this, WhoW](const TArray<uint8>& Pcm, int32 Rate, TSharedPtr<FJsonObject> Anim)
                {
                    bLineBusy = false;
                    ANpcAgent* Who = WhoW.Get();
                    if (!Who || Pcm.Num() < 2) return;
                    // arm the face track FIRST so it slaves to the audio from the first frame, then
                    // the NPC plays the voice on itself (audio-position-driven lip-sync — no drift)
                    const bool bFaced = Who->PlayFaceTrack(Anim);   // remote lip-sync; FaceTalk if unsolved
                    const float Dur = Who->PlayVoice(Pcm, Rate);
                    Who->PlayTalkGesture(Dur, !bFaced);
                }));
        }));
}

void AFerryPlayer::MoveForward(float V)
{
    if (V != 0.f)
    {
        const FRotator YawOnly(0.f, GetControlRotation().Yaw, 0.f);
        AddMovementInput(FRotationMatrix(YawOnly).GetUnitAxis(EAxis::X), V);
    }
}

void AFerryPlayer::MoveRight(float V)
{
    if (V != 0.f)
    {
        const FRotator YawOnly(0.f, GetControlRotation().Yaw, 0.f);
        AddMovementInput(FRotationMatrix(YawOnly).GetUnitAxis(EAxis::Y), V);
    }
}

void AFerryPlayer::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    const FString Region = FerryRegions::NameAt(GetActorLocation());
    if (LastRegion.IsEmpty())
    {
        LastRegion = Region;   // arrival pose; the session opener already frames the newcomer
        return;
    }
    if (Region != LastRegion)
    {
        LastRegion = Region;
        ObserveCrossing(Region);
    }
}

void AFerryPlayer::ObserveCrossing(const FString& Region)
{
    UMindClient* Mind = GetGameInstance() ? GetGameInstance()->GetSubsystem<UMindClient>() : nullptr;
    if (!Mind || !Mind->HasSession() || bObserveBusy || ANpcAgent::All.Num() == 0) return;
    bObserveBusy = true;

    const FString Observed = FString::Printf(TEXT("the traveler crosses to %s"), *Region);
    TArray<TPair<FString, FString>> Items;
    for (const ANpcAgent* A : ANpcAgent::All)
    {
        Items.Emplace(A->Slug, Observed);   // one taproom: everyone has line of sight
    }
    const FVector Where = GetActorLocation();
    Mind->Observe(GetWorld()->GetTimeSeconds() / 60.f, 0.1f,
        Items, FMindJsonReply::CreateWeakLambda(this, [this, Where](TSharedPtr<FJsonObject> Json)
        {
            bObserveBusy = false;
            if (!Json.IsValid()) return;
            const TArray<TSharedPtr<FJsonValue>>* Results = nullptr;
            if (!Json->TryGetArrayField(TEXT("results"), Results)) return;
            for (const TSharedPtr<FJsonValue>& V : *Results)
            {
                const TSharedPtr<FJsonObject> R = V->AsObject();
                if (!R.IsValid()) continue;
                FString Slug, React;
                R->TryGetStringField(TEXT("slug"), Slug);
                R->TryGetStringField(TEXT("react"), React);
                const bool bFlinch = R->GetBoolField(TEXT("flinch"));
                for (ANpcAgent* A : ANpcAgent::All)
                {
                    if (A->Slug != Slug) continue;
                    if (bFlinch)
                    {
                        A->FlinchAt(Where);   // pre-deliberative: the body registers it first
                    }
                    if (React == TEXT("act") || React == TEXT("speak"))
                    {
                        A->TakeBeat();        // the moment reached them — deliberate NOW, not next tick
                    }
                    if (React == TEXT("speak"))
                    {
                        UE_LOG(LogTemp, Display, TEXT("REACT %s wants to SPEAK (dialogue phase pending)"), *Slug);
                    }
                    break;
                }
            }
        }));
}
