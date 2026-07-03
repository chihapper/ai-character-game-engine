"""Bri face pass: hazel-green eyes, warm light-olive young skin, soft makeup.
Also triggers texture synthesis (required before build)."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
b = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Bri")

s = b.get_editor_property("skin_settings")
s.skin.face_texture_index = 0
s.skin.body_texture_index = 0
s.skin.roughness = 0.9
s.skin.u = 0.55   # warm, lightly sun-touched
s.skin.v = 0.52
sub.commit_skin_settings(b, s)
unreal.log("skin committed (tone %.2f/%.2f)" % (s.skin.u, s.skin.v))

e = b.get_editor_property("eyes_settings")
for eye in (e.eye_left, e.eye_right):
    eye.iris.primary_color_u = 0.30   # hazel-green
    eye.iris.primary_color_v = 0.55
    eye.iris.global_saturation = 1.4
sub.commit_eyes_settings(b, e)
unreal.log("eyes committed (hazel-green)")

m = b.get_editor_property("makeup_settings")
m.foundation.apply_foundation = True
m.foundation.intensity = 0.3
m.foundation.concealer = 0.6
sub.commit_makeup_settings(b, m)
unreal.log("makeup committed")

sft = b.get_editor_property("synthesized_face_textures")
unreal.log("synth textures: %d" % len(sft))
unreal.EditorLoadingAndSavingUtils.save_packages([b.get_package()], False)
unreal.log("BRI STYLED + SAVED")
