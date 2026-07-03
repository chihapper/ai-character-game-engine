"""Bri v4: smaller nose + smaller forehead + fuller/shorter face (blend toward Aera),
minimal makeup, alt young skin (neck creases), full voluminous hair."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
b = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Bri")

# geometry: 40% toward Aera (petite delicate features, rounder shorter face)
src = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Presets/Aera")
sub.try_add_object_to_edit(src)
sa = list(sub.get_face_model_coefficients(src))
ba = list(sub.get_face_model_coefficients(b))
if len(sa) == len(ba):
    W = 0.40
    out = [x if x == y else x * (1.0 - W) + y * W for x, y in zip(ba, sa)]
    sub.set_face_model_coefficients(b, out)
    sub.commit_face_state(b)
    unreal.log("blend 40%% Aera committed")
else:
    unreal.log("LEN MISMATCH — no blend")

# skin: lighter stays; try alt young texture set for a cleaner neck
s = b.get_editor_property("skin_settings")
s.skin.face_texture_index = 1
sub.commit_skin_settings(b, s)
unreal.log("skin tex -> 1")

# makeup: much less
m = b.get_editor_property("makeup_settings")
m.foundation.apply_foundation = True
m.foundation.intensity = 0.12
m.foundation.concealer = 0.35
sub.commit_makeup_settings(b, m)
unreal.log("makeup reduced")

# eyes: slightly less saturated
e = b.get_editor_property("eyes_settings")
e.eye_left.iris.global_saturation = 1.15
e.eye_right.iris.global_saturation = 1.15
sub.commit_eyes_settings(b, e)

# hair: full tousled long style
col = b.get_editor_property("internal_collection")
wi = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Grooms/Bindings/Hair/WI_Hair_L_MessyClumps")
key = col.try_add_item_from_wardrobe_item("Hair", wi)
if key:
    col.get_editor_property("default_instance").set_single_slot_selection("Hair", key)
    unreal.log("hair -> MessyClumps")

unreal.EditorLoadingAndSavingUtils.save_packages([b.get_package()], False)
unreal.log("BRI V4 SAVED")
