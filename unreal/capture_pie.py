"""Portraits inside PIE/simulate: use the game world + the CastCam copied in at play start."""
import unreal

world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
CAST = ["Della", "Corvin", "Edwin", "Bri"]
OUT = r"C:\Users\Alejandro\FerryInn\Saved\Screenshots\WindowsEditor"

caps = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.SceneCapture2D)
if not caps:
    unreal.log("NO SceneCapture2D in game world")
else:
    cap = caps[0]
    cc = cap.get_editor_property("capture_component2d")
    rt = cc.get_editor_property("texture_target")
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_TONE_CURVE_HDR)
    cc.set_editor_property("fov_angle", 45.0)
    actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
    by_label = {}
    for a in actors:
        by_label[a.get_actor_label()] = a
    for name in CAST:
        a = by_label.get("Cast_%s" % name)
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
        unreal.RenderingLibrary.export_render_target(world, rt, OUT, "PIE_%s.png" % name)
        unreal.log("PIE CAPTURED %s" % name)
unreal.log("PIE CAPTURE DONE")
