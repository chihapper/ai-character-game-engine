"""Find every MetaHumanCharacter asset anywhere (plugin content included) —
presets ship with valid textures; duplicating one avoids the texture-service asserts."""
import unreal

ar = unreal.AssetRegistryHelpers.get_asset_registry()
f = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/MetaHumanCharacter", "MetaHumanCharacter")],
                    recursive_paths=True, package_paths=["/"])
assets = ar.get_assets(f)
unreal.log("MHC ASSETS (%d):" % len(assets))
for a in assets:
    unreal.log("  %s" % a.package_name)

# also look at what the MetaHumanCharacter plugin mounts
roots = unreal.EditorAssetLibrary.list_assets("/MetaHumanCharacter", recursive=True, include_folder=False) if unreal.EditorAssetLibrary.does_directory_exist("/MetaHumanCharacter") else []
unreal.log("PLUGIN CONTENT (%d): %s" % (len(roots), ", ".join(str(r) for r in roots[:40])))
