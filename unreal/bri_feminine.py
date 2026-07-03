"""Bri v5: deterministic feminine recipe. Face = 0.40 Celeste + 0.35 Aera + 0.25 Vivian
(computed from source presets — resets accumulated blend drift). Lighter skin, arched
brows, soft lip tint."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
b = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Bri")

RECIPE = [("Celeste", 0.25), ("Aera", 0.40), ("Vivian", 0.35)]
arrays = []
for name, w in RECIPE:
    p = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Presets/%s" % name)
    sub.try_add_object_to_edit(p)
    arrays.append((list(sub.get_face_model_coefficients(p)), w))

n = len(arrays[0][0])
out = []
for i in range(n):
    vals = [a[i] for a, _ in arrays]
    if all(v == vals[0] for v in vals):
        out.append(vals[0])          # shared header/structure values stay untouched
    else:
        out.append(sum(a[i] * w for a, w in arrays))
sub.set_face_model_coefficients(b, out)
sub.commit_face_state(b)
unreal.log("feminine recipe committed (C40/A35/V25)")

s = b.get_editor_property("skin_settings")
s.skin.u = 0.34
s.skin.v = 0.50
sub.commit_skin_settings(b, s)
unreal.log("skin lighter (0.34)")

col = b.get_editor_property("internal_collection")
wi = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Grooms/Bindings/Eyebrows/WI_Eyebrows_M_SlightArch")
key = col.try_add_item_from_wardrobe_item("Eyebrows", wi)
if key:
    col.get_editor_property("default_instance").set_single_slot_selection("Eyebrows", key)
    unreal.log("brows -> SlightArch")

m = b.get_editor_property("makeup_settings")
unreal.log("lips struct: %s" % str(m.lips)[:220])
try:
    m.lips.color = unreal.LinearColor(0.45, 0.13, 0.12, 1.0)   # soft rose
    m.lips.opacity = 0.35
    sub.commit_makeup_settings(b, m)
    unreal.log("lip tint applied")
except Exception as e:
    unreal.log("lips ERR: %s" % e)

unreal.EditorLoadingAndSavingUtils.save_packages([b.get_package()], False)
unreal.log("BRI V5 SAVED")
