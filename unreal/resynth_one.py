"""Re-trigger face texture synthesis for NAME: open toolkit, commit current skin settings, save package."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
path = "/Game/Cast/%s" % NAME
ch = unreal.EditorAssetLibrary.load_asset(path)
unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).open_editor_for_assets([ch])
