using UnrealBuildTool;

public class FerryInn : ModuleRules
{
    public FerryInn(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core", "CoreUObject", "Engine", "InputCore",
            "HTTP", "Json", "JsonUtilities", "AudioMixer"
        });
    }
}
