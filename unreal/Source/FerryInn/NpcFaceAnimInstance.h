// The A2F face driver: a minimal anim instance that injects ARKit blendshape weights as
// anim curves and maps them through PA_MetaHuman_ARKit_Mapping (FAnimNode_PoseBlendNode —
// the node the shipped mapping asset is authored for). Its output curves feed the face's
// RigLogic post-process ABP, the same proven path the expression loops ride.
#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "AnimNodes/AnimNode_PoseBlendNode.h"
#include "NpcFaceAnimInstance.generated.h"

class UPoseAsset;

/** Source node: reference pose + whatever ARKit curve weights the agent set this frame. */
USTRUCT()
struct FAnimNode_ArkitCurveSource : public FAnimNode_Base
{
    GENERATED_BODY()

    TArray<FName> Names;
    TArray<float> Weights;

    virtual void Initialize_AnyThread(const FAnimationInitializeContext& Context) override {}
    virtual void CacheBones_AnyThread(const FAnimationCacheBonesContext& Context) override {}
    virtual void Update_AnyThread(const FAnimationUpdateContext& Context) override {}
    virtual void Evaluate_AnyThread(FPoseContext& Output) override;
};

USTRUCT()
struct FNpcFaceAnimProxy : public FAnimInstanceProxy
{
    GENERATED_BODY()

    FNpcFaceAnimProxy() {}
    FNpcFaceAnimProxy(UAnimInstance* InInstance) : FAnimInstanceProxy(InInstance) {}

    virtual void Initialize(UAnimInstance* InAnimInstance) override;
    virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
    virtual void UpdateAnimationNode(const FAnimationUpdateContext& InContext) override;
    virtual bool Evaluate(FPoseContext& Output) override;

    FAnimNode_ArkitCurveSource Source;
    FAnimNode_PoseBlendNode PoseBlend;
};

UCLASS(transient)
class FERRYINN_API UNpcFaceAnimInstance : public UAnimInstance
{
    GENERATED_BODY()

public:
    /** game thread: the agent pushes interpolated ARKit weights each tick */
    void SetArkitWeights(const TArray<FName>& InNames, const TArray<float>& InWeights);

    UPROPERTY(Transient)
    TObjectPtr<UPoseAsset> MappingAsset;

    FCriticalSection WeightsLock;
    TArray<FName> Names;
    TArray<float> Weights;

protected:
    virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;

    friend struct FNpcFaceAnimProxy;
};
