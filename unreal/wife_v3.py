"""Wife v3: +18% Lani (fuller cheeks, rounder lower face — per profile refs), arched brows,
warmer rose lip. Re-rig REQUIRED after this (geometry changed)."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
w = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Wife")
sub.try_add_object_to_edit(w)

la = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Presets/Lani")
sub.try_add_object_to_edit(la)
wa = list(sub.get_face_model_coefficients(w))
lb = list(sub.get_face_model_coefficients(la))
W = 0.18
out = [x if x == y else x * (1.0 - W) + y * W for x, y in zip(wa, lb)]
sub.set_face_model_coefficients(w, out)
sub.commit_face_state(w)
unreal.log("blend 18% Lani committed")

col = w.get_editor_property("internal_collection")
inst = col.get_editor_property("default_instance")
wi = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Grooms/Bindings/Eyebrows/WI_Eyebrows_M_SlightArch")
key = col.try_add_item_from_wardrobe_item("Eyebrows", wi)
if key:
    inst.set_single_slot_selection("Eyebrows", key)
    unreal.log("brows -> SlightArch")

m = w.get_editor_property("makeup_settings")
m.lips.type = unreal.MetaHumanCharacterLipsMakeupType.NATURAL
m.lips.color = unreal.LinearColor(0.42, 0.12, 0.13, 1.0)
m.lips.opacity = 0.3
sub.commit_makeup_settings(w, m)
unreal.log("lips warmed")

unreal.EditorLoadingAndSavingUtils.save_packages([w.get_package()], False)
unreal.log("V3 STYLED + SAVED")
