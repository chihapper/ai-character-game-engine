"""Inspect groom components + binding assets on the spawned cast."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for name in ["Della", "Corvin", "Edwin", "Bri"]:
    a = next((x for x in eas.get_all_level_actors() if x.get_actor_label() == "Cast_%s" % name), None)
    if not a:
        continue
    unreal.log("== %s" % name)
    for c in a.get_components_by_class(unreal.GroomComponent):
        g = c.get_editor_property("groom_asset")
        b = c.get_editor_property("binding_asset")
        att = c.get_attach_parent()
        unreal.log("  groom=%s binding=%s parent=%s" % (
            g.get_name() if g else None, b.get_name() if b else None,
            att.get_name() if att else None))
