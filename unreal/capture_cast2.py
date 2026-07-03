"""Portraits using a PRE-PLACED SceneCapture2D named CastCam (works inside simulate).
Creates CastCam + render target if missing (run once outside simulate to seed them)."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
CAST = ["Della", "Corvin", "Edwin", "Bri"]
OUT = r"C:\Users\Alejandro\FerryInn\Saved\Screenshots\WindowsEditor"
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

cap = next((x for x in eas.get_all_level_actors() if x.get_actor_label() == "CastCam"), None)
if not cap:
    cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    cap.set_actor_label("CastCam")
    unreal.log("CastCam created")

cc = cap.get_editor_property("capture_component2d")
rt = cc.get_editor_property("texture_target")
if not rt:
    rt = unreal.RenderingLibrary.create_render_target2d(world, 900, 1100, unreal.TextureRenderTargetFormat.RTF_RGBA8_SRGB)
    cc.set_editor_property("texture_target", rt)
cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_TONE_CURVE_HDR)
cc.set_editor_property("fov_angle", 45.0)

for name in CAST:
    a = next((x for x in eas.get_all_level_actors() if x.get_actor_label() == "Cast_%s" % name), None)
    if not a:
        unreal.log("NO ACTOR %s" % name)
        continue
    loc = a.get_actor_location()
    origin, extent = a.get_actor_bounds(False)
    head_z = origin.z + extent.z * 0.83
    cap.set_actor_location(unreal.Vector(loc.x - 130.0, loc.y, head_z), False, False)
    cap.set_actor_rotation(unreal.Rotator(0.0, 0.0, 0.0), False)
    for _ in range(4):
        cc.capture_scene()
    unreal.RenderingLibrary.export_render_target(world, rt, OUT, "Face_%s.png" % name)
    unreal.log("CAPTURED %s" % name)
unreal.log("CAPTURE2 DONE")
