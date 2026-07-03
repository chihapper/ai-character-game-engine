"""Import the local medieval outfit FBX (rigged, skinned) for MHC wardrobe fitting."""
import unreal

at = unreal.AssetToolsHelpers.get_asset_tools()
SRC = r"C:\Users\Alejandro\FerryCrossingPro\Assets\Resources\Q\Outfits\Exports\FBX (Unity)\Outfits"
DEST = "/Game/Cast/OutfitsRaw"
if not unreal.EditorAssetLibrary.does_directory_exist(DEST):
    unreal.EditorAssetLibrary.make_directory(DEST)

for name in ["Female_Peasant", "Male_Peasant"]:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", "%s\\%s.fbx" % (SRC, name))
    task.set_editor_property("destination_path", DEST)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("replace_existing", True)
    at.import_asset_tasks([task])
    unreal.log("%s -> %s" % (name, [str(p) for p in task.get_editor_property("imported_object_paths")]))

# what does the MHC outfit/wardrobe creation surface look like?
names = [n for n in dir(unreal) if "outfit" in n.lower() or "wardrobe" in n.lower()]
unreal.log("OUTFIT/WARDROBE CLASSES: %s" % ", ".join(names))
