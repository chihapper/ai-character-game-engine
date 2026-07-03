"""List plugin-mounted MetaHuman content directly."""
import unreal

for root in ("/MetaHumanCharacter", "/MetaHuman"):
    try:
        items = unreal.EditorAssetLibrary.list_assets(root, recursive=True, include_folder=False)
        unreal.log("%s (%d assets)" % (root, len(items)))
        # show anything preset-ish first, then a sample
        pres = [i for i in items if "preset" in str(i).lower()]
        unreal.log("  PRESET-ISH (%d): %s" % (len(pres), ", ".join(str(p) for p in pres[:30])))
        for i in items[:30]:
            unreal.log("  %s" % i)
    except Exception as e:
        unreal.log("%s ERR %s" % (root, e))
