"""MH_Wife: Sunita base + 20% Tuya roundness; warm-gold tone; full brows; long dark hair;
subtle liner. Photo ground truth: soft oval, fuller cheeks, large dark almond eyes."""
import unreal

at = unreal.AssetToolsHelpers.get_asset_tools()
sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
DST = "/Game/Cast/MH_Wife"

if not unreal.EditorAssetLibrary.does_asset_exist(DST):
    ok = unreal.EditorAssetLibrary.duplicate_asset("/MetaHumanCharacter/Optional/Presets/Sunita", DST)
    unreal.log("MH_Wife <- Sunita: %s" % ("OK" if ok else "FAILED"))
w = unreal.EditorAssetLibrary.load_asset(DST)
unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).open_editor_for_assets([w])
