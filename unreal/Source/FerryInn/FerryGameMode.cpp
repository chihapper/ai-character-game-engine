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
    struct FCastEntry { const TCHAR* Slug; const TCHAR* Handle; const TCHAR* Region; const TCHAR* Stance; };
    // slugs match game/scenarios/ferry_crossing.yaml — the same cast the Unity night ran
    const FCastEntry Cast[] = {
        { TEXT("della-fenwick"),             TEXT("the ferrywoman"),             TEXT("the bar"),          TEXT("working the bar") },
        { TEXT("corvin-ashgrave-inworld"),   TEXT("the watchful man"),           TEXT("a corner table"),   TEXT("nursing a cup, eyes on the door") },
        { TEXT("edwin-hale"),                TEXT("the soaked performer"),       TEXT("the far tables"),   TEXT("drying out, watching the room") },
        { TEXT("brielle-bri-castellano"),    TEXT("the bright young woman"),     TEXT("the long table"),   TEXT("cloak shed, taking in the room") },
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
        }
        ++Index;
    }
}
