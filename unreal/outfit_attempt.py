"""Wardrobe item with the peasant SkeletalMesh as principal asset — does the pipeline accept it?"""
import unreal

at = unreal.AssetToolsHelpers.get_asset_tools()
DEST = "/Game/Cast/Outfits"
if not unreal.EditorAssetLibrary.does_directory_exist(DEST):
    unreal.EditorAssetLibrary.make_directory(DEST)

wi = unreal.EditorAssetLibrary.load_asset(DEST + "/WI_FemalePeasant")
if not wi:
    wi = at.create_asset("WI_FemalePeasant", DEST, unreal.MetaHumanWardrobeItem, unreal.MetaHumanWardrobeItemFactory())
pa = wi.get_editor_property("principal_asset")
unreal.log("pa fields: %s" % [p for p in dir(pa) if not p.startswith("_") and p not in ("assign", "cast", "copy", "export_text", "import_text", "static_struct", "to_tuple", "set_editor_properties", "get_editor_property", "set_editor_property", "to_dict")])
mesh = unreal.EditorAssetLibrary.load_asset("/Game/Cast/OutfitsRaw/Female_Peasant")
try:
    pa.set_editor_property("asset", mesh)
    wi.set_editor_property("principal_asset", pa)
    unreal.log("principal set via .asset")
except Exception as e:
    unreal.log("set ERR: %s | trying to_dict" % e)
    unreal.log("pa dict: %s" % str(pa.to_dict() if hasattr(pa, "to_dict") else "n/a")[:300])
unreal.EditorAssetLibrary.save_asset(DEST + "/WI_FemalePeasant")
unreal.log("WI saved")
