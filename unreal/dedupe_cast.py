"""Keep one of each Cast_ actor, destroy stacked duplicates."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
seen = set()
killed = 0
for a in list(eas.get_all_level_actors()):
    lbl = a.get_actor_label()
    if lbl.startswith("Cast_"):
        if lbl in seen:
            eas.destroy_actor(a)
            killed += 1
        else:
            seen.add(lbl)
remaining = sorted(x.get_actor_label() for x in eas.get_all_level_actors() if x.get_actor_label().startswith("Cast_"))
unreal.log("deduped %d; remaining: %s" % (killed, remaining))
