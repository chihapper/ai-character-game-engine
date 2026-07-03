"""Bri: young and striking. Tone stays at DEFAULT (0.5,0.5) — lighter tones (u/v < 0.5)
hit the missing-BodyTexture assert. Youth reads through smooth tex 0, low roughness,
makeup, and bright eyes; the user sculpts the face geometry later."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
ch = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Bri")

s = ch.get_editor_property("skin_settings")
s.skin.face_texture_index = 0
s.skin.body_texture_index = 0
s.skin.roughness = 0.85
sub.commit_skin_settings(ch, s)
unreal.log("Bri skin committed")

m = ch.get_editor_property("makeup_settings")
m.foundation.apply_foundation = True
m.foundation.intensity = 0.35
m.foundation.concealer = 0.7
sub.commit_makeup_settings(ch, m)
unreal.log("Bri makeup committed")

e = ch.get_editor_property("eyes_settings")
e.eye_left.iris.primary_color_u = 0.35
e.eye_left.iris.primary_color_v = 0.62
e.eye_right.iris.primary_color_u = 0.35
e.eye_right.iris.primary_color_v = 0.62
sub.commit_eyes_settings(ch, e)
unreal.log("Bri eyes committed")

unreal.EditorAssetLibrary.save_asset("/Game/Cast/MH_Bri")
unreal.log("BRI LOOK SAVED")
