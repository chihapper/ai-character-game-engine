"""Wrap the imported FAB outfit assets in WardrobeItems and dress Bri + Wife."""
import unreal

at = unreal.AssetToolsHelpers.get_asset_tools()
oa = unreal.EditorAssetLibrary.load_asset("/Game/Wardrobe/OA_Shorts")
unreal.log("OA class: %s" % oa.get_class().get_name())

def make_wi(name, oa_path):
    p = "/Game/Wardrobe/WI_%s" % name
    wi = unreal.EditorAssetLibrary.load_asset(p)
    if not wi:
        wi = at.create_asset("WI_%s" % name, "/Game/Wardrobe", unreal.MetaHumanWardrobeItem, unreal.MetaHumanWardrobeItemFactory())
    pa = wi.get_editor_property("principal_asset")
    pa.set_editor_property("asset", unreal.EditorAssetLibrary.load_asset(oa_path))
    wi.set_editor_property("principal_asset", pa)
    unreal.EditorAssetLibrary.save_asset(p)
    return wi

def dress(char_path, items):
    ch = unreal.EditorAssetLibrary.load_asset(char_path)
    col = ch.get_editor_property("internal_collection")
    inst = col.get_editor_property("default_instance")
    for slot, wi in items:
        key = col.try_add_item_from_wardrobe_item(slot, wi)
        unreal.log("%s += %s in %s -> %s" % (char_path.split('/')[-1], wi.get_name(), slot, key is not None))
        if key:
            inst.set_single_slot_selection(slot, key)
    unreal.EditorLoadingAndSavingUtils.save_packages([ch.get_package()], False)

crop = make_wi("CropTop", "/Game/Wardrobe/OA_TCrop3QSlv")
shorts = make_wi("Shorts", "/Game/Wardrobe/OA_Shorts")
jump = make_wi("Jumpsuit", "/Game/Wardrobe/OA_KhaosMDF255")

dress("/Game/Cast/MH_Bri", [("Outfits", crop), ("Outfits", shorts)])
dress("/Game/Cast/MH_Wife", [("Outfits", jump)])
unreal.log("DRESSED")
