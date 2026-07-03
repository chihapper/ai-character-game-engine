"""Take the class path straight from MH_Della, wait for the registry scan, list all instances."""
import unreal

ar = unreal.AssetRegistryHelpers.get_asset_registry()
ar.wait_for_completion()

d = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Della")
cp = d.get_class().get_path_name()  # e.g. /Script/Module.MetaHumanCharacter
unreal.log("class path: %s" % cp)
pkg, cls = cp.rsplit(".", 1)
f = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath(pkg, cls)], recursive_paths=True, package_paths=["/"])
assets = ar.get_assets(f) or []
unreal.log("MHC ASSETS (%d):" % len(assets))
for a in assets:
    unreal.log("  %s" % a.package_name)

for root in ("/MetaHumanCharacter", "/MetaHuman", "/MetaHumanCharacterAssets"):
    ok = unreal.EditorAssetLibrary.does_directory_exist(root)
    unreal.log("root %s exists=%s" % (root, ok))
