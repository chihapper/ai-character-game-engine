import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
n = 0
for a in list(eas.get_all_level_actors()):
    lbl = a.get_actor_label()
    if lbl in ("BriPreview2", "WifePreview", "WifeCam") or lbl.startswith("WifeCand_"):
        eas.destroy_actor(a)
        n += 1
unreal.log("previews cleared: %d" % n)
