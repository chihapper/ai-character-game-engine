"""Blocking texture request, then the smallest possible skin commit (defaults, indices 0)
on Della. If this survives, the commit path is safe and looks can proceed stepwise."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
d = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Della")
sub.try_add_object_to_edit(d)

p = unreal.MetaHumanCharacterTextureRequestParams()
p.blocking = True
try:
    sub.request_texture_sources(d, p)
    unreal.log("blocking texture request: done")
except Exception as e:
    unreal.log("blocking request ERR: %s" % e)

bt = d.get_editor_property("body_textures")
unreal.log("body_textures: %s" % str(bt)[:400])

s = d.get_editor_property("skin_settings")
unreal.log("indices before commit: face=%s body=%s" % (s.skin.face_texture_index, s.skin.body_texture_index))
try:
    sub.commit_skin_settings(d, s)   # unmodified settings — pure canary
    unreal.log("CANARY COMMIT SURVIVED")
except Exception as e:
    unreal.log("canary commit ERR: %s" % e)
