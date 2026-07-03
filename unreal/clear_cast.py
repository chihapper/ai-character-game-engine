"""Remove all Cast_/CastPreview_/Lineup_ actors before a fresh spawn."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
n = 0
for a in list(eas.get_all_level_actors()):
    lbl = a.get_actor_label()
    if lbl.startswith("Cast_") or lbl.startswith("CastPreview_") or lbl.startswith("Lineup_"):
        eas.destroy_actor(a)
        n += 1
unreal.log("cleared %d actors" % n)
