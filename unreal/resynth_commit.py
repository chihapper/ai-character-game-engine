"""Step 2 of resynth (run after toolkit is open): commit skin, verify synth textures, save."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
path = "/Game/Cast/%s" % NAME
ch = unreal.EditorAssetLibrary.load_asset(path)
s = ch.get_editor_property("skin_settings")
sub.commit_skin_settings(ch, s)
sft = ch.get_editor_property("synthesized_face_textures")
unreal.log("%s synth textures: %d" % (NAME, len(sft)))
unreal.EditorLoadingAndSavingUtils.save_packages([ch.get_package()], False)
unreal.log("%s saved" % NAME)
