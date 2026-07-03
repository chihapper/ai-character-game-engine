"""Dedupe preview actors, then take a tight face shot of each cast member.
Actors stand at (-80, 150 + 120*i), facing +X. Camera 70cm in front, head height."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
seen = set()
actors = {}
for a in eas.get_all_level_actors():
    lbl = a.get_actor_label()
    if lbl.startswith("CastPreview_"):
        if lbl in seen:
            eas.destroy_actor(a)
            unreal.log("deduped %s" % lbl)
        else:
            seen.add(lbl)
            actors[lbl] = a

CAST = ["MH_Della", "MH_Corvin", "MH_Edwin", "MH_Bri"]
les = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

import unreal as u
IDX = globals().get("SHOT_IDX", 0)
name = CAST[IDX]
a = actors.get("CastPreview_%s" % name)
if not a:
    unreal.log("NO ACTOR for %s" % name)
else:
    loc = a.get_actor_location()
    # face height: probe actor bounds
    origin, extent = a.get_actor_bounds(False)
    head_z = origin.z + extent.z * 0.82
    cam = unreal.Vector(loc.x + 70.0, loc.y, head_z)
    rot = unreal.Rotator(0.0, 0.0, 180.0)  # pitch, roll, yaw -> look -X
    les.set_level_viewport_camera_info(cam, rot)
    unreal.log("camera set for %s (head_z=%.0f, bounds z extent=%.0f)" % (name, head_z, extent.z))
    unreal.SystemLibrary.execute_console_command(None, "HighResShot 1200x1400 filename=Face_%s" % name)
    unreal.log("shot queued for %s" % name)
