"""Style the re-based Bri: dark messy bob, full brows, thick lashes, hazel eyes,
subtle makeup, warm young skin. Toolkit must be open (run bri_style_open first)."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
b = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Bri")
col = b.get_editor_property("internal_collection")

SWAPS = {
    "Hair": "/MetaHumanCharacter/Optional/Grooms/Bindings/Hair/WI_Hair_M_BobMessy",
    "Eyebrows": "/MetaHumanCharacter/Optional/Grooms/Bindings/Eyebrows/WI_Eyebrows_M_Full",
    "Eyelashes": "/MetaHumanCharacter/Optional/Grooms/Bindings/Eyelashes/WI_Eyelashes_L_ThickCurl",
}
inst = col.get_editor_property("default_instance")
unreal.log("instance: %s" % inst)
im = [m for m in dir(inst) if "slot" in m.lower() or "select" in m.lower()]
unreal.log("instance slot methods: %s" % ", ".join(im))

for slot, path in SWAPS.items():
    wi = unreal.EditorAssetLibrary.load_asset(path)
    if not wi:
        # try alternate folder layouts
        alt = path.replace("/Grooms/Hair/", "/Grooms/").replace("/Grooms/Eyebrows/", "/Grooms/").replace("/Grooms/Eyelashes/", "/Grooms/")
        wi = unreal.EditorAssetLibrary.load_asset(alt)
    if not wi:
        unreal.log("MISSING wardrobe item for %s: %s" % (slot, path))
        continue
    key = col.try_add_item_from_wardrobe_item(slot, wi)
    unreal.log("%s += %s -> key %s" % (slot, wi.get_name(), key))
    if key:
        try:
            inst.set_single_slot_selection(slot, key)
            unreal.log("%s selected" % slot)
        except Exception as e:
            unreal.log("select ERR %s: %s" % (slot, e))
