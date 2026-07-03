"""Casting step 1: create the remaining character assets, open them for editing,
and REPORT the parameter surfaces (face coefficients, skin settings shapes) so the
look passes are written against reality."""
import unreal

at = unreal.AssetToolsHelpers.get_asset_tools()
ar = unreal.AssetRegistryHelpers.get_asset_registry()
sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)

CAST = ["MH_Della", "MH_Corvin", "MH_Edwin", "MH_Bri"]
chars = {}
for name in CAST:
    path = "/Game/Cast/%s" % name
    existing = unreal.EditorAssetLibrary.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
    if existing:
        chars[name] = existing
        unreal.log("EXISTS: %s" % path)
    else:
        a = at.create_asset(name, "/Game/Cast", unreal.MetaHumanCharacter, unreal.MetaHumanCharacterFactoryNew())
        chars[name] = a
        unreal.log("CREATED: %s" % (a.get_path_name() if a else "FAILED " + name))

# open Della for editing and inspect the surfaces
d = chars.get("MH_Della")
if d:
    added = sub.try_add_object_to_edit(d)
    unreal.log("EDIT-OPEN Della: %s" % added)
    try:
        co = sub.get_face_model_coefficients(d)
        unreal.log("FACE COEFFS type=%s repr=%s" % (type(co).__name__, str(co)[:400]))
    except Exception as e:
        unreal.log("FACE COEFFS ERR: %s" % e)
    # what does the character asset itself expose?
    props = [p for p in dir(d) if not p.startswith("_")]
    unreal.log("CHAR PROPS: %s" % ", ".join(props[:60]))
