using UnrealBuildTool;

public class FerryUnreal : ModuleRules
{
    public FerryUnreal(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core", "CoreUObject", "Engine", "InputCore",
            "HTTP", "Json", "JsonUtilities", "AudioMixer"
        });
    }
}
