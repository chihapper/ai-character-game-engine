using UnrealBuildTool;

public class FerryUnrealTarget : TargetRules
{
    public FerryUnrealTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("FerryUnreal");
    }
}
