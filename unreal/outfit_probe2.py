"""Create a test ChaosOutfitAsset + WardrobeItem, dump their editable properties."""
import unreal

at = unreal.AssetToolsHelpers.get_asset_tools()
DEST = "/Game/Cast/Outfits"
if not unreal.EditorAssetLibrary.does_directory_exist(DEST):
    unreal.EditorAssetLibrary.make_directory(DEST)

oa = unreal.EditorAssetLibrary.load_asset(DEST + "/OA_FemalePeasant")
if not oa:
    oa = at.create_asset("OA_FemalePeasant", DEST, unreal.ChaosOutfitAsset, unreal.ChaosOutfitAssetFactory())
unreal.log("outfit asset: %s" % oa)
props = unreal.ChaosOutfitAsset.static_class()
plist = []
it = oa.get_editor_property
for name in ("outfit", "sized_outfit_sources", "outfit_sources", "body_size", "pieces", "cloth_asset", "source"):
    try:
        plist.append("%s=%s" % (name, str(it(name))[:120]))
    except Exception:
        pass
unreal.log("props found: %s" % plist)

wi = unreal.EditorAssetLibrary.load_asset(DEST + "/WI_FemalePeasant")
if not wi:
    wi = at.create_asset("WI_FemalePeasant", DEST, unreal.MetaHumanWardrobeItem, unreal.MetaHumanWardrobeItemFactory())
unreal.log("wardrobe item: %s" % wi)
wprops = []
for name in ("principal_asset", "thumbnail", "slot_name", "principal_asset_class"):
    try:
        wprops.append("%s=%s" % (name, str(wi.get_editor_property(name))[:120]))
    except Exception:
        pass
unreal.log("wi props: %s" % wprops)
