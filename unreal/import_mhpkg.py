"""Import one .mhpkg (set PKG to the file path) into /Game/Wardrobe."""
import unreal

at = unreal.AssetToolsHelpers.get_asset_tools()
if not unreal.EditorAssetLibrary.does_directory_exist("/Game/Wardrobe"):
    unreal.EditorAssetLibrary.make_directory("/Game/Wardrobe")
task = unreal.AssetImportTask()
task.set_editor_property("filename", PKG)
task.set_editor_property("destination_path", "/Game/Wardrobe")
task.set_editor_property("automated", True)
task.set_editor_property("save", True)
task.set_editor_property("replace_existing", True)
at.import_asset_tasks([task])
unreal.log("IMPORTED: %s" % [str(p) for p in task.get_editor_property("imported_object_paths")][:8])
