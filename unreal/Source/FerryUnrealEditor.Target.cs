using UnrealBuildTool;

public class FerryUnrealEditorTarget : TargetRules
{
    public FerryUnrealEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("FerryUnreal");
    }
}
