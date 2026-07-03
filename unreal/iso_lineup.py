"""Spread lineup actors along an isolated strip, all facing -X toward the camera line."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
acts = sorted([a for a in eas.get_all_level_actors() if a.get_actor_label().startswith("Lineup_")],
              key=lambda a: a.get_actor_label())
for i, a in enumerate(acts):
    a.set_actor_location(unreal.Vector(-3500.0, 400.0 * i, 0.0), False, False)
    a.set_actor_rotation(unreal.Rotator(0.0, 0.0, -90.0), False)
unreal.log("ISO: %d actors placed" % len(acts))
for a in acts:
    unreal.log("  %s" % a.get_actor_label())
