"""Preview-spawn the wife-likeness base candidates and mugshot each via SceneCapture."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
OUT = r"C:\Users\Alejandro\FerryInn\Saved\Screenshots\WindowsEditor"
NAMES = ["Sunita", "Asha", "Tuya", "Etta", "Lani"]

# clear old lineup previews
for a in list(eas.get_all_level_actors()):
    if a.get_actor_label().startswith("WifeCand_"):
        eas.destroy_actor(a)

rt = unreal.RenderingLibrary.create_render_target2d(world, 800, 950, unreal.TextureRenderTargetFormat.RTF_RGBA8_SRGB)
cap = eas.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
cap.set_actor_label("WifeCam")
cc = cap.get_editor_property("capture_component2d")
cc.set_editor_property("texture_target", rt)
cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_TONE_CURVE_HDR)
cc.set_editor_property("fov_angle", 30.0)

for i, n in enumerate(NAMES):
    ch = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Presets/%s" % n)
    sub.try_add_object_to_edit(ch)
    a = sub.spawn_meta_human_actor(ch, False)
    if not a:
        unreal.log("SPAWN FAIL %s" % n)
        continue
    a.set_actor_label("WifeCand_%s" % n)
    a.set_actor_location(unreal.Vector(-3500.0, 300.0 * i, 0.0), False, False)
    a.set_actor_rotation(unreal.Rotator(0.0, 0.0, 90.0), False)   # face -X toward camera
    origin, ext = a.get_actor_bounds(False)
    head_z = origin.z + ext.z * 0.86
    cap.set_actor_location(unreal.Vector(-3500.0 - 90.0, 300.0 * i, head_z), False, False)
    for _ in range(4):
        cc.capture_scene()
    unreal.RenderingLibrary.export_render_target(world, rt, OUT, "WifeCand_%s.png" % n)
    unreal.log("captured %s" % n)
unreal.log("WIFE LINEUP DONE")
