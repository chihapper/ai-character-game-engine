"""Della hair -> gray updo buns; measure table bounds near the two clipping anchors."""
import unreal

# 1) Della hair
b = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Della")
col = b.get_editor_property("internal_collection")
wi = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Grooms/Bindings/Hair/WI_Hair_S_UpdoBuns")
if not wi:
    wi = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Grooms/Bindings/Hair/WI_Hair_S_Updo")
key = col.try_add_item_from_wardrobe_item("Hair", wi)
if key:
    col.get_editor_property("default_instance").set_single_slot_selection("Hair", key)
    unreal.EditorLoadingAndSavingUtils.save_packages([b.get_package()], False)
    unreal.log("Della hair -> %s, saved" % wi.get_name())

# 2) tables near the long table (-30,-540) and far tables (-150,1050)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in eas.get_all_level_actors():
    lbl = a.get_actor_label().lower()
    if "table" in lbl or "bench" in lbl:
        o, e = a.get_actor_bounds(False)
        for cx, cy, tag in ((-30, -540, "LONG"), (-150, 1050, "FAR")):
            if abs(o.x - cx) < 300 and abs(o.y - cy) < 350:
                unreal.log("%s %s o=(%.0f,%.0f) ext=(%.0f,%.0f)" % (tag, a.get_actor_label(), o.x, o.y, e.x, e.y))
