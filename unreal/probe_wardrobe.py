"""Bri's collection: slots, current items, and every available Hair wardrobe item on disk."""
import unreal

b = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Bri")
col = b.get_editor_property("internal_collection")
unreal.log("slots: %s" % list(col.get_slot_names()))
for k in col.get_all_item_keys():
    try:
        unreal.log("  item %s slot=%s name=%s" % (k, col.get_item_slot_name(k), col.get_item_display_name(k)))
    except Exception as e:
        unreal.log("  item %s ERR %s" % (k, e))

# all hair grooms shipped with Core Data
items = unreal.EditorAssetLibrary.list_assets("/MetaHumanCharacter/Optional/Grooms", recursive=True, include_folder=False)
hair = [str(i) for i in items if "/Hair" in str(i) and "WI_" in str(i)]
unreal.log("HAIR WARDROBE ITEMS (%d):" % len(hair))
for h in hair[:40]:
    unreal.log("  %s" % h.split("/")[-1].split(".")[0])
