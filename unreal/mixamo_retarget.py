"""Mixamo -> MetaHuman: import the X Bot clips and batch-retarget onto the game skeleton.
All-auto pipeline: apply_auto_generated_retarget_definition + auto_map_chains + auto_align."""
import unreal
import os

SRC_DIR = r"C:\Users\Alejandro\Downloads"
DEST = "/Game/Cast/Anims/Mixamo"
CLIPS = ["Sitting Talking", "Sitting Idle", "Sitting Laughing", "Laughing", "Pointing",
         "Waving", "Shrugging", "Thinking", "Yawn", "Surprised", "Neck Stretching"]

at = unreal.AssetToolsHelpers.get_asset_tools()

def import_fbx(path, dest, skeleton=None, mesh=True, name=""):
    ui = unreal.FbxImportUI()
    ui.set_editor_property("automated_import_should_detect_type", False)
    ui.set_editor_property("import_mesh", mesh)
    ui.set_editor_property("import_as_skeletal", mesh)
    ui.set_editor_property("import_animations", True)
    ui.set_editor_property("import_materials", False)
    ui.set_editor_property("import_textures", False)
    ui.set_editor_property("create_physics_asset", False)
    ui.set_editor_property("mesh_type_to_import",
                           unreal.FBXImportType.FBXIT_SKELETAL_MESH if mesh else unreal.FBXImportType.FBXIT_ANIMATION)
    if skeleton:
        ui.set_editor_property("skeleton", skeleton)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", path)
    task.set_editor_property("destination_path", dest)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("options", ui)
    at.import_asset_tasks([task])
    return [str(p) for p in task.get_editor_property("imported_object_paths")]

if not unreal.EditorAssetLibrary.does_directory_exist(DEST + "/Source"):
    unreal.EditorAssetLibrary.make_directory(DEST + "/Source")

# 1) first clip WITH mesh -> creates X Bot skeleton
first = import_fbx(os.path.join(SRC_DIR, "X Bot@Sitting Talking.fbx"), DEST + "/Source", name="XBot_SittingTalking")
unreal.log("first import: %s" % first)
