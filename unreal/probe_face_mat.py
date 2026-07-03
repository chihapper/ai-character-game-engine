"""Why is the face gray? Inspect Della's face mesh materials + basecolor textures."""
import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
a = next((x for x in eas.get_all_level_actors() if x.get_actor_label() == "Cast_Della"), None)
comps = a.get_components_by_class(unreal.SkeletalMeshComponent)
for c in comps:
    unreal.log("COMP %s mesh=%s" % (c.get_name(), c.get_skeletal_mesh_asset().get_name() if c.get_skeletal_mesh_asset() else None))
    for i, m in enumerate(c.get_materials()):
        unreal.log("  slot %d: %s" % (i, m.get_path_name() if m else None))

# the built face textures on disk
for t in ("T_Face_Basecolor", "T_Face_Basecolor_Animated_CM1"):
    p = "/Game/Cast/Unpacked/Della/Face/Textures/%s" % t
    if unreal.EditorAssetLibrary.does_asset_exist(p):
        tex = unreal.EditorAssetLibrary.load_asset(p)
        unreal.log("%s: %dx%d vt=%s" % (t, tex.blueprint_get_size_x(), tex.blueprint_get_size_y(),
                                        tex.get_editor_property("virtual_texture_streaming")))
    else:
        unreal.log("%s: MISSING" % t)

# face MI parameter check
mi_path = "/Game/Cast/Unpacked/Della/Face/Materials/MI_Face_Head"
hits = [str(x) for x in unreal.EditorAssetLibrary.list_assets("/Game/Cast/Unpacked/Della/Face/Materials", recursive=False, include_folder=False)]
unreal.log("face MIs: %s" % ", ".join(h.split("/")[-1] for h in hits))
