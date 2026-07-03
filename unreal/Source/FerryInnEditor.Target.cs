using UnrealBuildTool;

public class FerryInnEditorTarget : TargetRules
{
    public FerryInnEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("FerryInn");
    }
}
