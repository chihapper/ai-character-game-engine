"""Rotate a lineup row to face -X and shoot it from the west. Set ROW before exec."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

rows = {}
for a in eas.get_all_level_actors():
    lbl = a.get_actor_label()
    if lbl.startswith("Lineup_"):
        r = int(lbl.split("_")[1])
        rows.setdefault(r, []).append(a)

acts = rows.get(ROW, [])
ys = []
for a in acts:
    a.set_actor_rotation(unreal.Rotator(0.0, 0.0, -90.0), False)  # forward -X (default fwd is -Y at yaw 0)
    ys.append(a.get_actor_location().y)
if acts:
    cy = (min(ys) + max(ys)) / 2.0
    rx = acts[0].get_actor_location().x
    les.set_level_viewport_camera_info(unreal.Vector(rx - 330.0, cy, 165.0), unreal.Rotator(0.0, 0.0, 0.0))
    unreal.SystemLibrary.execute_console_command(None, "HighResShot 1920x700 filename=Row_%d" % ROW)
    unreal.log("row %d: %d actors, shot queued" % (ROW, len(acts)))
else:
    unreal.log("row %d empty" % ROW)
