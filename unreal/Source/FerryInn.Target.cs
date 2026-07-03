using UnrealBuildTool;

public class FerryInnTarget : TargetRules
{
    public FerryInnTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("FerryInn");
    }
}
