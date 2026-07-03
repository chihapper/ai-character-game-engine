"""Core Data installed — find the shipped character presets and the API to apply them."""
import unreal

# presets folder mounts under the plugin content root
for root in ("/MetaHumanCharacter/Optional/Presets", "/MetaHumanCharacter/Presets", "/MetaHumanCharacter/Optional"):
    if unreal.EditorAssetLibrary.does_directory_exist(root):
        items = unreal.EditorAssetLibrary.list_assets(root, recursive=True, include_folder=False)
        unreal.log("%s: %d assets" % (root, len(items)))
        for i in items[:60]:
            unreal.log("  %s" % i)
        break
else:
    unreal.log("no preset dir found under /MetaHumanCharacter")

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
pm = [m for m in dir(sub) if "preset" in m.lower() or "import" in m.lower()]
unreal.log("PRESET/IMPORT METHODS: %s" % ", ".join(pm))
