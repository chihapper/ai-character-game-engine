"""Auto IK rigs for XBot + MH body, retargeter with auto-mapped chains, batch retarget all clips."""
import unreal

at = unreal.AssetToolsHelpers.get_asset_tools()
DEST = "/Game/Cast/Anims"

xbot_mesh = unreal.EditorAssetLibrary.load_asset(DEST + "/Source/Mx_Talking")
mh_mesh = unreal.EditorAssetLibrary.load_asset("/Game/Cast/Unpacked/Corvin/Body/SKM_MH_Corvin_BodyMesh")
unreal.log("meshes: %s / %s" % (xbot_mesh.get_name(), mh_mesh.get_name()))

def make_rig(name, mesh):
    path = DEST + "/" + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.EditorAssetLibrary.load_asset(path)
    rig = at.create_asset(name, DEST, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
    c = unreal.IKRigController.get_controller(rig)
    c.set_skeletal_mesh(mesh)
    ok = c.apply_auto_generated_retarget_definition()
    unreal.log("%s auto-characterize: %s" % (name, ok))
    unreal.EditorAssetLibrary.save_asset(path)
    return rig

src_rig = make_rig("IK_XBot", xbot_mesh)
tgt_rig = make_rig("IK_MHBody", mh_mesh)

rt_path = DEST + "/RTG_XBot_to_MH"
if unreal.EditorAssetLibrary.does_asset_exist(rt_path):
    rtg = unreal.EditorAssetLibrary.load_asset(rt_path)
else:
    rtg = at.create_asset("RTG_XBot_to_MH", DEST, unreal.IKRetargeter, unreal.IKRetargetFactory())
rc = unreal.IKRetargeterController.get_controller(rtg)
ms = [m for m in dir(rc) if "ik_rig" in m.lower() or "preview" in m.lower()]
unreal.log("rc rig methods: %s" % ms)
try:
    rc.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, src_rig)
    rc.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, tgt_rig)
    unreal.log("rigs set")
except Exception as e:
    unreal.log("set_ik_rig ERR: %s" % e)
try:
    rc.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
    unreal.log("chains mapped (exact)")
except Exception as e:
    try:
        rc.auto_map_chains(unreal.AutoMapChainType.FUZZY, True)
        unreal.log("chains mapped (fuzzy)")
    except Exception as e2:
        unreal.log("auto_map ERR: %s / %s" % (e, e2))
try:
    rc.auto_align_all_bones(unreal.RetargetSourceOrTarget.SOURCE)
    unreal.log("source pose auto-aligned")
except Exception as e:
    unreal.log("auto_align ERR: %s" % e)
unreal.EditorAssetLibrary.save_asset(rt_path)

# batch retarget every source clip
items = [str(i).split(".")[0] for i in unreal.EditorAssetLibrary.list_assets(DEST + "/Source", recursive=False, include_folder=False)]
anims = []
for p in items:
    a = unreal.EditorAssetLibrary.load_asset(p)
    if isinstance(a, unreal.AnimSequence):
        anims.append(unreal.EditorAssetLibrary.find_asset_data(p))
unreal.log("source anims: %d" % len(anims))
op = unreal.IKRetargetBatchOperation()
try:
    out = op.duplicate_and_retarget(anims, xbot_mesh, mh_mesh, rtg,
                                    search="Mx_", replace="MHG_", target_path=DEST + "/MH")
    unreal.log("RETARGETED %d assets" % len(out))
except Exception as e:
    unreal.log("batch ERR: %s" % e)

# the batch only creates in-memory assets — without this, a restart deletes them all
if unreal.EditorAssetLibrary.does_asset_exist(DEST + "/MH/MHG_Talking_Anim"):
    unreal.EditorAssetLibrary.rename_asset(DEST + "/MH/MHG_Talking_Anim", DEST + "/MH/MHG_Talking")
saved = 0
for p in unreal.EditorAssetLibrary.list_assets(DEST + "/MH", recursive=True, include_folder=False):
    if unreal.EditorAssetLibrary.save_asset(str(p).split(".")[0]):
        saved += 1
unreal.log("SAVED %d retargeted clips to disk" % saved)
