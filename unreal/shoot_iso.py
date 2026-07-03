"""Face shot of lineup actor IDX (sorted by label). Camera west of the face, looking +X."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
acts = sorted([a for a in eas.get_all_level_actors() if a.get_actor_label().startswith("Lineup_")],
              key=lambda a: a.get_actor_label())
a = acts[IDX]
loc = a.get_actor_location()
origin, extent = a.get_actor_bounds(False)
head_z = origin.z + extent.z * 0.80
les.set_level_viewport_camera_info(unreal.Vector(loc.x - 110.0, loc.y, head_z), unreal.Rotator(0.0, 0.0, 0.0))
name = a.get_actor_label().split("_", 3)[-1]
unreal.SystemLibrary.execute_console_command(None, "HighResShot 800x1000 filename=P_%02d_%s" % (IDX, name))
unreal.log("shot %s (head_z %.0f)" % (name, head_z))
