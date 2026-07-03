"""Mixamo (with skin) -> MetaHuman: import all clips, auto-build IK rigs, batch retarget."""
import unreal
import os

SRC = r"C:\Users\Alejandro\Downloads"
DEST = "/Game/Cast/Anims"
CLIPS = ["Talking", "Sitting Talking", "Sitting Idle", "Sitting Laughing", "Laughing",
         "Pointing Gesture", "Waving", "Shrugging", "Thinking", "Yawn", "Surprised",
         "Neck Stretching", "Leaning On A Wall"]

at = unreal.AssetToolsHelpers.get_asset_tools()
for d in (DEST, DEST + "/Source", DEST + "/MH"):
    if not unreal.EditorAssetLibrary.does_directory_exist(d):
        unreal.EditorAssetLibrary.make_directory(d)

skeleton = None
for c in CLIPS:
    ui = unreal.FbxImportUI()
    ui.set_editor_property("automated_import_should_detect_type", False)
    ui.set_editor_property("import_mesh", skeleton is None)
    ui.set_editor_property("import_as_skeletal", True)
    ui.set_editor_property("import_animations", True)
    ui.set_editor_property("import_materials", False)
    ui.set_editor_property("import_textures", False)
    ui.set_editor_property("create_physics_asset", False)
    ui.set_editor_property("mesh_type_to_import",
                           unreal.FBXImportType.FBXIT_SKELETAL_MESH if skeleton is None else unreal.FBXImportType.FBXIT_ANIMATION)
    if skeleton:
        ui.set_editor_property("skeleton", skeleton)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", os.path.join(SRC, c + ".fbx"))
    task.set_editor_property("destination_path", DEST + "/Source")
    task.set_editor_property("destination_name", "Mx_" + c.replace(" ", ""))
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("options", ui)
    at.import_asset_tasks([task])
    paths = [str(p) for p in task.get_editor_property("imported_object_paths")]
    unreal.log("%s -> %s" % (c, paths))
    if skeleton is None and paths:
        for p in paths:
            a = unreal.EditorAssetLibrary.load_asset(p.split(".")[0])
            if isinstance(a, unreal.SkeletalMesh):
                skeleton = a.get_editor_property("skeleton")
                unreal.log("XBot skeleton: %s" % skeleton.get_path_name())
unreal.log("IMPORTS DONE")
