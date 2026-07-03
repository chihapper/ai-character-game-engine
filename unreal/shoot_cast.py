"""Portrait of one built cast member (set IDX 0..3). They stand at (-80, 150*i), facing -X (yaw 90).
Camera 120cm out on -X at face height, looking +X."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
CAST = ["Della", "Corvin", "Edwin", "Bri"]
name = CAST[IDX]
a = next((x for x in eas.get_all_level_actors() if x.get_actor_label() == "Cast_%s" % name), None)
if not a:
    unreal.log("NO ACTOR Cast_%s" % name)
else:
    loc = a.get_actor_location()
    origin, extent = a.get_actor_bounds(False)
    head_z = origin.z + extent.z * 0.83
    les.set_level_viewport_camera_info(unreal.Vector(loc.x - 120.0, loc.y, head_z), unreal.Rotator(0.0, 0.0, 0.0))
    unreal.SystemLibrary.execute_console_command(None, "HighResShot 900x1100 filename=Cast_%s" % name)
    unreal.log("shot Cast_%s (head_z %.0f)" % (name, head_z))
