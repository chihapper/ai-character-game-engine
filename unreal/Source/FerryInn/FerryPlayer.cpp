#include "FerryPlayer.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "FerryRegions.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "MindClient.h"
#include "NpcAgent.h"

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
