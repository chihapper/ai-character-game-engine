"""Re-base Bri on the Vivian preset (softer, rounder face per the user's reference)."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in list(eas.get_all_level_actors()):
    if a.get_actor_label() == "Cast_Bri":
        eas.destroy_actor(a)
        unreal.log("removed Cast_Bri actor")

if unreal.EditorAssetLibrary.does_asset_exist("/Game/Cast/MH_Bri"):
    unreal.EditorAssetLibrary.delete_asset("/Game/Cast/MH_Bri")
    unreal.log("old MH_Bri deleted")
ok = unreal.EditorAssetLibrary.duplicate_asset("/MetaHumanCharacter/Optional/Presets/Vivian", "/Game/Cast/MH_Bri")
unreal.log("MH_Bri <- Vivian: %s" % ("OK" if ok else "FAILED"))
if ok:
    unreal.EditorAssetLibrary.save_asset("/Game/Cast/MH_Bri")
