"""Proof shots of embodied agents in simulate: wide room + Della closeup."""
import unreal

les = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
world = les.get_game_world()
agents = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
npc = [a for a in agents if a.get_class().get_name() == "NpcAgent"]
unreal.log("agents found: %d" % len(npc))
for a in npc:
    unreal.log("  %s at %s" % (a.get_editor_property("Slug"), a.get_actor_location()))

if MODE == "wide":
    les.set_level_viewport_camera_info(unreal.Vector(-750.0, -850.0, 320.0), unreal.Rotator(0.0, -12.0, 57.0))
    unreal.SystemLibrary.execute_console_command(world, "HighResShot 1600x900 filename=Embodied_Wide")
    unreal.log("wide shot queued")
else:
    della = next((a for a in npc if "della" in str(a.get_editor_property("Slug"))), None)
    if della:
        loc = della.get_actor_location()
        fwd = della.get_actor_forward_vector()
        cam = unreal.Vector(loc.x + fwd.x * 150.0, loc.y + fwd.y * 150.0, loc.z + 60.0)
        rot = unreal.MathLibrary.find_look_at_rotation(cam, unreal.Vector(loc.x, loc.y, loc.z + 55.0))
        les.set_level_viewport_camera_info(cam, rot)
        unreal.SystemLibrary.execute_console_command(world, "HighResShot 1100x900 filename=Embodied_Della")
        unreal.log("della shot queued")
