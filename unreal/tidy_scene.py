"""Remove capture props, report cast presence."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
n = 0
for a in list(eas.get_all_level_actors()):
    if a.get_actor_label() in ("CastCam", "PreviewBri"):
        eas.destroy_actor(a)
        n += 1
cast = [a.get_actor_label() for a in eas.get_all_level_actors() if a.get_actor_label().startswith("Cast_")]
unreal.log("props removed: %d; cast in level: %s" % (n, cast))
