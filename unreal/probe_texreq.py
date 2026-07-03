"""body_textures is empty -> commits assert. request_texture_sources should populate.
Inspect the params struct, fire the request for Della, and see what changes."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)

p = unreal.MetaHumanCharacterTextureRequestParams()
unreal.log("REQ PARAMS: %s" % str(p))
props = [x for x in dir(p) if not x.startswith("_")]
unreal.log("REQ PARAM PROPS: %s" % ", ".join(props))

d = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Della")
sub.try_add_object_to_edit(d)
try:
    sub.request_texture_sources(d, p)
    unreal.log("request_texture_sources: fired")
except Exception as e:
    unreal.log("request_texture_sources ERR: %s" % e)

bt = d.get_editor_property("body_textures")
unreal.log("body_textures after: %s" % str(bt)[:400])
unreal.log("synth after: %s" % str(d.get_editor_property("synthesized_face_textures"))[:200])
unreal.log("high_res: %s" % d.get_editor_property("has_high_resolution_textures"))
