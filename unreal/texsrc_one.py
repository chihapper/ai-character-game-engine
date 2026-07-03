"""Async texture-source download for one character (set NAME). blocking=True asserts."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
ch = unreal.EditorAssetLibrary.load_asset("/Game/Cast/%s" % NAME)
sub.try_add_object_to_edit(ch)
p = unreal.MetaHumanCharacterTextureRequestParams()
p.blocking = False
sub.request_texture_sources(ch, p)
unreal.log("%s TEXTURE SOURCES REQUESTED (async)" % NAME)
