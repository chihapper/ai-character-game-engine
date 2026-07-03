"""Remove lineup + clay previews, spawn the four BUILT MetaHuman blueprints in the taproom."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in list(eas.get_all_level_actors()):
    lbl = a.get_actor_label()
    if lbl.startswith("Lineup_") or lbl.startswith("CastPreview_"):
        eas.destroy_actor(a)

CAST = ["Della", "Corvin", "Edwin", "Bri"]
for i, n in enumerate(CAST):
    bp = unreal.EditorAssetLibrary.load_asset("/Game/Cast/Unpacked/%s/BP_%s" % (n, n))
    if not bp:
        unreal.log("MISSING BP_%s" % n)
        continue
    a = eas.spawn_actor_from_object(bp, unreal.Vector(-80.0, 0.0 + 150.0 * i, 0.0), unreal.Rotator(0.0, 0.0, 90.0))
    if a:
        a.set_actor_label("Cast_%s" % n)
        unreal.log("SPAWNED Cast_%s" % n)
    else:
        unreal.log("SPAWN FAIL %s" % n)
unreal.log("BUILT CAST IN LEVEL")
