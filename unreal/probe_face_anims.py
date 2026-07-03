"""Facial idle loops: which skeleton do they target, and what do the built faces use?"""
import unreal

items = [str(i) for i in unreal.EditorAssetLibrary.list_assets("/MetaHumanCharacter/Optional/Animation", recursive=True, include_folder=False)]
falls = [i for i in items if "facialloop" in i.lower()]
unreal.log("facial loops: %d" % len(falls))
f1 = unreal.EditorAssetLibrary.load_asset(falls[0].split(".")[0])
unreal.log("sample %s -> skel %s" % (f1.get_name(), f1.get_editor_property("skeleton").get_path_name()))

# split body-track vs face-track clips
for i in falls[:6]:
    unreal.log("  %s" % i.split("/")[-1].split(".")[0])

fm = unreal.EditorAssetLibrary.load_asset("/Game/Cast/Unpacked/Della/Face/SKM_MH_Della_FaceMesh")
unreal.log("Della face skel: %s" % fm.get_editor_property("skeleton").get_path_name())
