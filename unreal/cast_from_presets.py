"""Replace the blank /Game/Cast assets with duplicates of the chosen presets,
then layer per-character deltas (texture synthesis now works — Core Data installed)."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
CHOICE = {
    "MH_Della": "Sook-ja",
    "MH_Bri": "Celeste",
    "MH_Corvin": "Bruce",
    "MH_Edwin": "Orlando",
}

for name, preset in CHOICE.items():
    dst = "/Game/Cast/%s" % name
    if unreal.EditorAssetLibrary.does_asset_exist(dst):
        unreal.EditorAssetLibrary.delete_asset(dst)
    src = "/MetaHumanCharacter/Optional/Presets/%s" % preset
    ok = unreal.EditorAssetLibrary.duplicate_asset(src, dst)
    unreal.log("%s <- %s : %s" % (name, preset, "OK" if ok else "FAILED"))
    if ok:
        unreal.EditorAssetLibrary.save_asset(dst)
unreal.log("CAST DUPLICATED")
