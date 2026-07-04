// One NPC's life in the world — the Unity client's proven loop, re-bodied: an idle cadence of
// perceive -> choose -> enact. The engine picks ONLY from afforded options (grounding by
// construction); the mind lives on :8001 and never learns what a nav query is.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "NpcAgent.generated.h"

class UMindClient;

UCLASS()
class FERRYINN_API ANpcAgent : public ACharacter
{
    GENERATED_BODY()

public:
    ANpcAgent();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mind")
    FString Slug;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mind")
    FString Handle;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mind")
    FString Stance;

    /** per-character clip paths, set by the game mode before AttachMetaHumanBody */
    FString FaceLoopPath;
    FString IdleAltPath;
    FString FaceSex;   // "f" or "m" — selects the gendered expression-loop variants

    /** all living agents, for percepts and options */
    static TArray<ANpcAgent*> All;

    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    virtual void Tick(float DeltaSeconds) override;

    /** a grounded action beat: compose situation, offer options, enact the mind's pick */
    void TakeBeat();

    /** dress the agent in a built MetaHuman blueprint; hides the capsule placeholder */
    void AttachMetaHumanBody(UClass* BodyClass);

    /** pre-deliberative orienting response: turn toward the event, startle crosses the face */
    void FlinchAt(const FVector& Where);

    /** talking body language for the duration of a spoken reply, then settle back to idle */
    void PlayTalkGesture(float Seconds);

private:
    UPROPERTY()
    AActor* BodyActor = nullptr;

    UPROPERTY()
    UStaticMeshComponent* PlaceholderBody = nullptr;

    UPROPERTY()
    USkeletalMeshComponent* BodyMesh = nullptr;

    UPROPERTY()
    USkeletalMeshComponent* FaceMesh = nullptr;

    UPROPERTY()
    UAnimSequence* IdleAnim = nullptr;

    UPROPERTY()
    UAnimSequence* WalkAnim = nullptr;

    UPROPERTY()
    UAnimSequence* IdleAltAnim = nullptr;

    UPROPERTY()
    UAnimSequence* FaceLoop = nullptr;

    UPROPERTY()
    UAnimSequence* CurrentIdle = nullptr;

    void VaryIdle();

    UPROPERTY()
    TArray<UAnimSequence*> Gestures;

    /** engine-chosen reaction faces: tag ("happy", "sad", ...) -> loop */
    UPROPERTY()
    TMap<FString, UAnimSequence*> FaceReactions;

    FTimerHandle IdleVarietyTimer;
    FTimerHandle GestureReturnTimer;
    FTimerHandle FaceReturnTimer;
    bool bAnimWalking = false;

    FString ComposeSituation() const;
    TArray<FString> ComposeOptions() const;
    void Enact(const FString& Action, const FString& Reason);
    void WalkTo(const FVector& Target);

    UMindClient* Mind() const;

    FTimerHandle LifeTimer;
    bool bBusy = false;
    bool bWalking = false;
    FVector WalkTarget = FVector::ZeroVector;
};
