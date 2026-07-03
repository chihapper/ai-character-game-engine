"""Make the game skeleton accept the plugin's locomotion clips + probe garment MI params."""
import unreal

gs = unreal.EditorAssetLibrary.load_asset("/Game/Cast/Built/Common/Female/Medium/NormalWeight/Body/metahuman_base_skel")
ps = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Female/Medium/NormalWeight/Body/metahuman_base_skel")
comp = list(gs.get_editor_property("compatible_skeletons"))
paths = [str(c.get_path_name() if hasattr(c, "get_path_name") else c) for c in comp]
if not any("MetaHumanCharacter" in p for p in paths):
    comp.append(ps)
    gs.set_editor_property("compatible_skeletons", comp)
    unreal.EditorAssetLibrary.save_asset(gs.get_path_name().split(".")[0])
    unreal.log("plugin skeleton registered compatible + saved")
else:
    unreal.log("already compatible")

mi = unreal.EditorAssetLibrary.load_asset("/Game/Cast/Unpacked/Della/Clothing/MI_WI_DefaultGarment_M_DG_bodyShapeA_Shirt")
if mi:
    vals = mi.get_editor_property("vector_parameter_values")
    unreal.log("shirt MI vector params: %s" % [str(v.parameter_info.name) for v in vals])
    svals = mi.get_editor_property("scalar_parameter_values")
    unreal.log("shirt MI scalar params: %s" % [str(v.parameter_info.name) for v in svals][:15])
    parent = mi.get_editor_property("parent")
    unreal.log("parent: %s" % parent.get_name())
