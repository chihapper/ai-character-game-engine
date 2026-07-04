#include "NpcFaceAnimInstance.h"

#include "Animation/PoseAsset.h"

void FAnimNode_ArkitCurveSource::Evaluate_AnyThread(FPoseContext& Output)
{
    Output.ResetToRefPose();
    const int32 N = FMath::Min(Names.Num(), Weights.Num());
    for (int32 I = 0; I < N; ++I)
    {
        Output.Curve.Set(Names[I], Weights[I]);
    }
}

void FNpcFaceAnimProxy::Initialize(UAnimInstance* InAnimInstance)
{
    FAnimInstanceProxy::Initialize(InAnimInstance);
    if (UNpcFaceAnimInstance* Inst = Cast<UNpcFaceAnimInstance>(InAnimInstance))
    {
        PoseBlend.PoseAsset = Inst->MappingAsset;
    }
    PoseBlend.SourcePose.SetLinkNode(&Source);
    FAnimationInitializeContext InitContext(this);
    PoseBlend.Initialize_AnyThread(InitContext);
}

void FNpcFaceAnimProxy::PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds)
{
    FAnimInstanceProxy::PreUpdate(InAnimInstance, DeltaSeconds);
    // game-thread snapshot of the agent-set weights into the worker-thread node
    if (UNpcFaceAnimInstance* Inst = Cast<UNpcFaceAnimInstance>(InAnimInstance))
    {
        FScopeLock Hold(&Inst->WeightsLock);
        Source.Names = Inst->Names;
        Source.Weights = Inst->Weights;
    }
}

void FNpcFaceAnimProxy::UpdateAnimationNode(const FAnimationUpdateContext& InContext)
{
    UpdateCounter.Increment();
    PoseBlend.Update_AnyThread(InContext);
}

bool FNpcFaceAnimProxy::Evaluate(FPoseContext& Output)
{
    PoseBlend.Evaluate_AnyThread(Output);
    return true;
}

void UNpcFaceAnimInstance::SetArkitWeights(const TArray<FName>& InNames, const TArray<float>& InWeights)
{
    FScopeLock Hold(&WeightsLock);
    Names = InNames;
    Weights = InWeights;
}

FAnimInstanceProxy* UNpcFaceAnimInstance::CreateAnimInstanceProxy()
{
    return new FNpcFaceAnimProxy(this);
}
