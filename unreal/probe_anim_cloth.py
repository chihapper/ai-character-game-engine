"""What animation + clothing does Core Data ship? And where exactly is the bar counter?"""
import unreal

# animations
for root in ("/MetaHumanCharacter/Optional/Animation", "/MetaHumanCharacter/Animation"):
    if unreal.EditorAssetLibrary.does_directory_exist(root):
        items = [str(i) for i in unreal.EditorAssetLibrary.list_assets(root, recursive=True, include_folder=False)]
        unreal.log("%s: %d assets" % (root, len(items)))
        for i in items[:40]:
            unreal.log("  %s" % i.split("/")[-1].split(".")[0])

# clothing wardrobe items
croot = "/MetaHumanCharacter/Optional/Clothing"
if unreal.EditorAssetLibrary.does_directory_exist(croot):
    items = [str(i) for i in unreal.EditorAssetLibrary.list_assets(croot, recursive=True, include_folder=False)]
    wi = [i.split("/")[-1].split(".")[0] for i in items if "/WI_" in i or i.split("/")[-1].startswith("WI_")]
    unreal.log("CLOTHING items (%d WI of %d assets):" % (len(wi), len(items)))
    for w in wi[:40]:
        unreal.log("  %s" % w)

# bar geometry: find counter-ish actors and dump bounds
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in eas.get_all_level_actors():
    lbl = a.get_actor_label().lower()
    if "bar" in lbl or "counter" in lbl:
        origin, ext = a.get_actor_bounds(False)
        unreal.log("BAR? %s origin=(%.0f,%.0f,%.0f) ext=(%.0f,%.0f,%.0f)" %
                   (a.get_actor_label(), origin.x, origin.y, origin.z, ext.x, ext.y, ext.z))
