"""build_meta_human for one character (set NAME first). Produces the textured,
rigged assembly under /Game/Cast/Built/<name>."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
ch = unreal.EditorAssetLibrary.load_asset("/Game/Cast/%s" % NAME)
sub.try_add_object_to_edit(ch)

p = unreal.MetaHumanCharacterEditorBuildParameters()
p.absolute_build_path = ""
p.common_folder_path = "/Game/Cast/Built/Common"
p.name_override = NAME.replace("MH_", "")
try:
    unreal.log("pipeline_type default: %s ; quality: %s" % (p.pipeline_type, p.pipeline_quality))
except Exception as e:
    unreal.log("param read err %s" % e)

try:
    sub.build_meta_human(ch, p)
    unreal.log("%s BUILD DONE" % NAME)
except Exception as e:
    unreal.log("%s BUILD ERR: %s" % (NAME, e))
