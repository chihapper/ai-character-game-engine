"""Viewport face shot during simulate. IDX 0..3. Uses game world for actor positions."""
import unreal

world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
CAST = ["Della", "Corvin", "Edwin", "Bri"]
name = CAST[IDX]
actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
a = next((x for x in actors if x.get_actor_label() == "Cast_%s" % name), None)
if not a:
    unreal.log("NO ACTOR %s" % name)
else:
    loc = a.get_actor_location()
    origin, extent = a.get_actor_bounds(False)
    head_z = origin.z + extent.z * 0.83
    les = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    les.set_level_viewport_camera_info(unreal.Vector(loc.x - 110.0, loc.y, head_z), unreal.Rotator(0.0, 0.0, 0.0))
    unreal.SystemLibrary.execute_console_command(world, "HighResShot 900x1100 filename=Hair_%s" % name)
    unreal.log("PIE viewport shot %s" % name)
