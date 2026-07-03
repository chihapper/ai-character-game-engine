"""What preset machinery does MetaHumanCharacter expose? And what can the editor subsystem do?"""
import unreal

presetish = [n for n in dir(unreal) if "metahuman" in n.lower() and ("preset" in n.lower() or "template" in n.lower())]
unreal.log("MH PRESET CLASSES: %s" % ", ".join(presetish))

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
methods = [m for m in dir(sub) if not m.startswith("_")]
unreal.log("SUBSYSTEM METHODS (%d): %s" % (len(methods), ", ".join(methods)))

# any plugin-shipped preset character assets?
ar = unreal.AssetRegistryHelpers.get_asset_registry()
hits = []
for path in ("/MetaHumanCharacter", "/Game/MetaHumans", "/MetaHuman"):
    for a in ar.get_assets_by_path(path, recursive=True):
        n = str(a.asset_name).lower()
        if "preset" in n or str(a.asset_class_path.asset_name) == "MetaHumanCharacter":
            hits.append(str(a.package_name))
unreal.log("PRESET ASSETS (%d): %s" % (len(hits), ", ".join(hits[:20])))
