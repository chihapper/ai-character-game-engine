import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
n = 0
for a in list(eas.get_all_level_actors()):
    if a.get_actor_label().startswith("Cast_"):
        eas.destroy_actor(a)
        n += 1
unreal.log("removed %d statues" % n)
