"""MH_Wife styling pass (toolkit open): geometry blend, tone, grooms, makeup."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
w = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Wife")

# geometry: 80% Sunita + 20% Tuya (rounder, fuller cheeks)
tu = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Presets/Tuya")
sub.try_add_object_to_edit(tu)
wa = list(sub.get_face_model_coefficients(w))
ta = list(sub.get_face_model_coefficients(tu))
if len(wa) == len(ta):
    W = 0.20
    out = [x if x == y else x * (1.0 - W) + y * W for x, y in zip(wa, ta)]
    sub.set_face_model_coefficients(w, out)
    sub.commit_face_state(w)
    unreal.log("blend 20% Tuya committed")

# skin: warm gold, a touch lighter than Sunita's 0.644
s = w.get_editor_property("skin_settings")
s.skin.u = 0.55
s.skin.v = 0.60
s.skin.face_texture_index = 80   # Sunita's warm complexion set
s.skin.body_texture_index = 0
sub.commit_skin_settings(w, s)
unreal.log("skin committed (0.55/0.60 tex 80)")

col = w.get_editor_property("internal_collection")
inst = col.get_editor_property("default_instance")
for slot, path in (("Hair", "/MetaHumanCharacter/Optional/Grooms/Bindings/Hair/WI_Hair_L_Straight"),
                   ("Eyebrows", "/MetaHumanCharacter/Optional/Grooms/Bindings/Eyebrows/WI_Eyebrows_M_Full"),
                   ("Eyelashes", "/MetaHumanCharacter/Optional/Grooms/Bindings/Eyelashes/WI_Eyelashes_L_ThickCurl")):
    wi = unreal.EditorAssetLibrary.load_asset(path)
    key = col.try_add_item_from_wardrobe_item(slot, wi)
    if key:
        inst.set_single_slot_selection(slot, key)
        unreal.log("%s -> %s" % (slot, wi.get_name()))

m = w.get_editor_property("makeup_settings")
m.foundation.apply_foundation = True
m.foundation.intensity = 0.15
m.foundation.concealer = 0.4
m.lips.type = unreal.MetaHumanCharacterLipsMakeupType.NATURAL
m.lips.color = unreal.LinearColor(0.32, 0.10, 0.10, 1.0)
m.lips.opacity = 0.25
sub.commit_makeup_settings(w, m)
unreal.log("makeup committed")

unreal.EditorLoadingAndSavingUtils.save_packages([w.get_package()], False)
unreal.log("MH_WIFE STYLED + SAVED")
