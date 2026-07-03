#include "FerryGameMode.h"

#include "FerryRegions.h"
#include "MindClient.h"
#include "NpcAgent.h"

void AFerryGameMode::BeginPlay()
{
    Super::BeginPlay();
    UMindClient* Mind = GetGameInstance()->GetSubsystem<UMindClient>();
    Mind->CreateSession(TEXT("ferry_crossing.yaml"),
        FMindJsonReply::CreateWeakLambda(this, [this](TSharedPtr<FJsonObject> Json)
        {
            if (!Json.IsValid())
            {
                UE_LOG(LogTemp, Error, TEXT("FerryGameMode: mind server unreachable — is :8001 up?"));
                return;
            }
            UE_LOG(LogTemp, Display, TEXT("FerryGameMode: session live, spawning cast"));
            SpawnCast();
        }));
}

void AFerryGameMode::SpawnCast()
{
    struct FCastEntry { const TCHAR* Slug; const TCHAR* Handle; const TCHAR* Region; const TCHAR* Stance; const TCHAR* BodyPath; float OpeningYaw; };
    // slugs match game/scenarios/ferry_crossing.yaml — the same cast the Unity night ran;
    // bodies are the built MetaHumans under /Game/Cast/Unpacked; yaw = facing the room from their post
    const FCastEntry Cast[] = {
        { TEXT("della-fenwick"),             TEXT("the ferrywoman"),             TEXT("behind the bar"),   TEXT("working the bar"),                    TEXT("/Game/Cast/Unpacked/Della/BP_Della.BP_Della_C"),   180.f },
        { TEXT("corvin-ashgrave-inworld"),   TEXT("the watchful man"),           TEXT("a corner table"),   TEXT("nursing a cup, eyes on the door"),    TEXT("/Game/Cast/Unpacked/Corvin/BP_Corvin.BP_Corvin_C"),  30.f },
        { TEXT("edwin-hale"),                TEXT("the soaked performer"),       TEXT("the far tables"),   TEXT("drying out, watching the room"),      TEXT("/Game/Cast/Unpacked/Edwin/BP_Edwin.BP_Edwin_C"),    -90.f },
        { TEXT("brielle-bri-castellano"),    TEXT("the bright young woman"),     TEXT("the long table"),   TEXT("cloak shed, taking in the room"),     TEXT("/Game/Cast/Unpacked/Bri/BP_Bri.BP_Bri_C"),           90.f },
    };
    int32 Index = 0;
    for (const FCastEntry& C : Cast)
    {
        const FVector Anchor = FerryRegions::Anchor(C.Region) + FVector(40.f * Index, 30.f, 92.f);
        FActorSpawnParameters Params;
        Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
        ANpcAgent* Agent = GetWorld()->SpawnActor<ANpcAgent>(ANpcAgent::StaticClass(), Anchor, FRotator::ZeroRotator, Params);
        if (Agent)
        {
            Agent->Slug = C.Slug;
            Agent->Handle = C.Handle;
            Agent->Stance = C.Stance;
            Agent->SetActorRotation(FRotator(0.f, C.OpeningYaw, 0.f));
            if (UClass* BodyClass = StaticLoadClass(AActor::StaticClass(), nullptr, C.BodyPath))
            {
                Agent->AttachMetaHumanBody(BodyClass);
            }
            else
            {
                UE_LOG(LogTemp, Warning, TEXT("FerryGameMode: no body at %s — %s keeps the capsule"), C.BodyPath, C.Slug);
            }
        }
        ++Index;
    }
}
