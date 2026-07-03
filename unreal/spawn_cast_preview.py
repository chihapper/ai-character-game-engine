"""Spawn all four cast members into the level for face screenshots.
Line them up in the open floor near the taproom middle, facing +X."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

existing = {a.get_actor_label() for a in eas.get_all_level_actors()
            if a.get_actor_label().startswith("CastPreview_")}

CAST = ["MH_Della", "MH_Corvin", "MH_Edwin", "MH_Bri"]
x0, y0 = -80.0, 150.0   # middle of the taproom
spawned = []
for i, name in enumerate(CAST):
    if ("CastPreview_%s" % name) in existing:
        unreal.log("KEEP %s" % name)
        spawned.append(name)
        continue
    ch = unreal.EditorAssetLibrary.load_asset("/Game/Cast/%s" % name)
    sub.try_add_object_to_edit(ch)
    try:
        a = sub.spawn_meta_human_actor(ch, False)  # transient spawns get GC'd before we can shoot them
        a.set_actor_label("CastPreview_%s" % name)
        a.set_actor_location(unreal.Vector(x0, y0 + 120.0 * i, 0.0), False, False)
        a.set_actor_rotation(unreal.Rotator(0.0, 0.0, 0.0), False)
        spawned.append(name)
        unreal.log("SPAWNED %s" % name)
    except Exception as e:
        unreal.log("SPAWN ERR %s: %s" % (name, e))
unreal.log("PREVIEW SPAWNS: %s" % ", ".join(spawned))
