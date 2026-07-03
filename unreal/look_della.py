"""Della: the ferrywoman, aged hard by the river. Toolkit must already be open."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
d = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Della")

s = d.get_editor_property("skin_settings")
s.skin.face_texture_index = 4
s.skin.body_texture_index = 4
s.skin.roughness = 1.4
sub.commit_skin_settings(d, s)
unreal.log("Della skin committed (face/body tex 4)")

h = d.get_editor_property("head_model_settings")
h.teeth.worn_down = 0.75
h.teeth.receding_gums = 0.55
h.teeth.upper_shift = 0.2
h.eyelashes.salt_and_pepper = 0.95
h.eyelashes.lightness = 0.75
sub.commit_head_model_settings(d, h)
unreal.log("Della head model committed (worn teeth, gray lashes)")

unreal.EditorAssetLibrary.save_asset("/Game/Cast/MH_Della")
unreal.log("DELLA LOOK SAVED")
