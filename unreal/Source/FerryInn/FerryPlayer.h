// The TRAVELER — the player's body in the taproom. Their presence is a real event: crossing
// the room generates first-person observations for every NPC (the react recipe over real
// witnesses); minds appraise, bodies flinch, characters decide.
#pragma once

#include "CoreMinimal.h"
#include "AudioCaptureCore.h"
#include "GameFramework/Character.h"
#include "FerryPlayer.generated.h"

class UCameraComponent;
class ANpcAgent;

UCLASS()
class FERRYINN_API AFerryPlayer : public ACharacter
{
    GENERATED_BODY()

public:
    AFerryPlayer();

    virtual void Tick(float DeltaSeconds) override;
    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;

private:
    void MoveForward(float V);
    void MoveRight(float V);

    /** the react recipe, client half: everyone in the taproom witnesses the crossing */
    void ObserveCrossing(const FString& Region);

    /** push-to-talk: hold to record, release to send the clip through STT -> nearest mind */
    void StartTalk();
    void StopTalk();
    void HandleSpokenLine(const FString& Line);
    ANpcAgent* NearestAgent(float MaxDist) const;

    UPROPERTY()
    UCameraComponent* Camera = nullptr;

    FString LastRegion;
    bool bObserveBusy = false;

    Audio::FAudioCapture AudioCapture;
    FCriticalSection CaptureLock;
    TArray<int16> CaptureSamples;
    int32 CaptureRate = 16000;
    bool bTalking = false;
    bool bLineBusy = false;
};
