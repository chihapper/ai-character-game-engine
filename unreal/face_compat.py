"""Register plugin face skeleton as compatible with the game's built face skeleton."""
import unreal

items = [str(i) for i in unreal.EditorAssetLibrary.list_assets("/MetaHumanCharacter/Optional/Animation", recursive=True, include_folder=False)]
fclip_path = next(i for i in items if "_f_facialloop_happy_f" in i).split(".")[0]
fclip = unreal.EditorAssetLibrary.load_asset(fclip_path)
pskel = fclip.get_editor_property("skeleton")
unreal.log("face clip skel: %s" % pskel.get_path_name())

gskel = unreal.EditorAssetLibrary.load_asset("/Game/Cast/Built/Common/Face/Face_Archetype_Skeleton")
comp = list(gskel.get_editor_property("compatible_skeletons"))
if not any("MetaHuman" in str(getattr(c, "get_path_name", lambda: c)()) for c in comp):
    comp.append(pskel)
    gskel.set_editor_property("compatible_skeletons", comp)
    unreal.EditorAssetLibrary.save_asset("/Game/Cast/Built/Common/Face/Face_Archetype_Skeleton")
    unreal.log("face skeleton compatibility registered + saved")
else:
    unreal.log("already compatible")
