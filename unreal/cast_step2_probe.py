"""Casting step 2 probe: dump the semantic parameter structs + template machinery."""
import unreal

d = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Della")
for prop in ("skin_settings", "head_model_settings", "eyes_settings", "makeup_settings",
             "fixed_body_type", "face_evaluation_settings"):
    try:
        v = d.get_editor_property(prop)
        unreal.log("%s = %s" % (prop, str(v)[:500]))
    except Exception as e:
        unreal.log("%s ERR %s" % (prop, e))

unreal.log("TEMPLATE TYPES: %s" % [x for x in dir(unreal.MetaHumanCharacterTemplateType) if not x.startswith("_")])
sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
unreal.log("import_from_template doc: %s" % (sub.import_from_template.__doc__ or "")[:300])
unreal.log("body types: %s" % [x for x in dir(unreal.MetaHumanBodyType) if not x.startswith("_")][:30] if hasattr(unreal, "MetaHumanBodyType") else "no MetaHumanBodyType")
