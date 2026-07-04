// Boots the night: one mind-server session, four bodies at their opening places.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "FerryGameMode.generated.h"

UCLASS()
class FERRYINN_API AFerryGameMode : public AGameModeBase
{
    GENERATED_BODY()

public:
    AFerryGameMode();

    virtual void BeginPlay() override;

private:
    void SpawnCast();
};
