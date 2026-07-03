"""Spawn preset candidates in role rows outside the tavern's west door for triage shots.
Row 0: older women (Della). Row 1: young women (Bri). Row 2: hard men (Corvin). Row 3: performers (Edwin)."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

ROWS = [
    ["Etta", "Sook-ja", "Grace", "Vivian", "Tuya"],
    ["Aera", "Celeste", "Jelena", "Lani", "Zuri", "Ada"],
    ["Victor", "Dominic", "Bruce", "Mikel"],
    ["Orlando", "Mateo", "Trey", "Isaiah"],
]

existing = {a.get_actor_label() for a in eas.get_all_level_actors()}
BX, BY = -1200.0, -400.0   # open ground west of the tavern door (-760,135)
for r, row in enumerate(ROWS):
    for c, name in enumerate(row):
        lbl = "Lineup_%d_%d_%s" % (r, c, name)
        if lbl in existing:
            unreal.log("KEEP %s" % lbl)
            continue
        ch = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Presets/%s" % name)
        if not ch:
            unreal.log("MISSING preset %s" % name)
            continue
        sub.try_add_object_to_edit(ch)
        a = sub.spawn_meta_human_actor(ch, False)
        if not a:
            unreal.log("SPAWN FAIL %s" % name)
            continue
        a.set_actor_label(lbl)
        a.set_actor_location(unreal.Vector(BX - 200.0 * r, BY + 130.0 * c, 0.0), False, False)
        a.set_actor_rotation(unreal.Rotator(0.0, 0.0, 0.0), False)
        unreal.log("SPAWNED %s" % lbl)
unreal.log("LINEUP DONE")
