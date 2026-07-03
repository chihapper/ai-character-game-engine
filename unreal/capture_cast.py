"""Viewport-independent portraits: SceneCapture2D -> RenderTarget -> PNG export.
Works with the editor unfocused/occluded. Captures all four in one pass."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
CAST = ["Della", "Corvin", "Edwin", "Bri"]
OUT = r"C:\Users\Alejandro\FerryInn\Saved\Screenshots\WindowsEditor"

rt = unreal.RenderingLibrary.create_render_target2d(unreal.EditorLevelLibrary.get_editor_world(),
                                                    900, 1100, unreal.TextureRenderTargetFormat.RTF_RGBA8_SRGB)
cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
cc = cap.get_editor_property("capture_component2d")
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
    for _ in range(6):   # first captures prime virtual-texture feedback; later ones get streamed mips
        cc.capture_scene()
    ok = unreal.RenderingLibrary.export_render_target(unreal.EditorLevelLibrary.get_editor_world(),
                                                      rt, OUT, "Face_%s.png" % name)
    unreal.log("CAPTURED %s -> %s" % (name, ok))

eas.destroy_actor(cap)
unreal.log("CAPTURE PASS DONE")
