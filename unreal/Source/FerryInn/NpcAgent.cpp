#include "NpcAgent.h"

#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "FerryRegions.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "MindClient.h"
#include "TimerManager.h"
#include "UObject/ConstructorHelpers.h"

TArray<ANpcAgent*> ANpcAgent::All;

ANpcAgent::ANpcAgent()
{
    PrimaryActorTick.bCanEverTick = true;
    GetCapsuleComponent()->SetCapsuleSize(30.f, 90.f);
    GetCharacterMovement()->MaxWalkSpeed = 160.f;   // a tavern is not a racetrack

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
    All.Remove(this);
    Super::EndPlay(Reason);
}

void ANpcAgent::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
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
            FString Action, Reason;
            Json->TryGetStringField(TEXT("action"), Action);
            Json->TryGetStringField(TEXT("reason"), Reason);
            UE_LOG(LogTemp, Display, TEXT("MINDBEAT %s -> '%s' (%s)"), *Slug, *Action, *Reason);
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
    bWalking = true;
}
