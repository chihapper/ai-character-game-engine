"""Dress with the PACK-SHIPPED wardrobe items (correct pipelines included)."""
import unreal

def dress(char_path, single, extras):
    ch = unreal.EditorAssetLibrary.load_asset(char_path)
    col = ch.get_editor_property("internal_collection")
    inst = col.get_editor_property("default_instance")
    wi = unreal.EditorAssetLibrary.load_asset(single)
    key = col.try_add_item_from_wardrobe_item("Outfits", wi)
    unreal.log("%s: %s -> %s" % (char_path.split('/')[-1], wi.get_name(), key is not None))
    if key:
        inst.set_single_slot_selection("Outfits", key)
    for ep in extras:
        ewi = unreal.EditorAssetLibrary.load_asset(ep)
        ek = col.try_add_item_from_wardrobe_item("Outfits", ewi)
        if ek:
            sel = unreal.MetaHumanPipelineSlotSelection()
            sel.set_editor_property("slot_name", "Outfits")
            sel.set_editor_property("selected_item", ek)
            r = inst.try_add_slot_selection(sel)
            unreal.log("  + %s additive: %s" % (ewi.get_name(), r))
    unreal.EditorLoadingAndSavingUtils.save_packages([ch.get_package()], False)

dress("/Game/Cast/MH_Bri", "/Game/Wardrobe/WI_OA_TCrop3QSlv", ["/Game/Wardrobe/WI_OA_Shorts"])
dress("/Game/Cast/MH_Wife", "/Game/Wardrobe/WI_KhaosMDF255", [])
unreal.log("DRESSED v2")
