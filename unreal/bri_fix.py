"""Bri fix pass: lighter skin, tighter skin (less high-frequency droop), narrower nose
via a partial coefficient blend toward Celeste (narrow elegant bridge).
Toolkit for MH_Bri must be open."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
b = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Bri")

# 1) lighter, still slightly warm skin
s = b.get_editor_property("skin_settings")
unreal.log("tone before: u=%.2f v=%.2f" % (s.skin.u, s.skin.v))
s.skin.u = 0.42
s.skin.v = 0.50
s.skin.roughness = 0.9
sub.commit_skin_settings(b, s)
unreal.log("skin committed (lighter: 0.42/0.50)")

# 2) tighter skin: damp high-frequency geometry detail (sag/droop texture)
fe = b.get_editor_property("face_evaluation_settings")
unreal.log("eval before: global=%.2f hf=%.2f" % (fe.global_delta, fe.high_frequency_delta))
fe.high_frequency_delta = 0.5
try:
    b.set_editor_property("face_evaluation_settings", fe)
    unreal.log("eval set via property")
except Exception as e:
    unreal.log("eval property set failed (%s) — trying via face state commit anyway" % e)

# 3) nose bridge: blend coefficients 30%% toward Celeste, header ints preserved
cel = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Presets/Celeste")
sub.try_add_object_to_edit(cel)
ca = list(sub.get_face_model_coefficients(cel))
ba = list(sub.get_face_model_coefficients(b))
unreal.log("coeff lens: bri=%d celeste=%d" % (len(ba), len(ca)))
if len(ba) == len(ca):
    W = 0.30
    out = []
    changed = 0
    for i, (x, y) in enumerate(zip(ba, ca)):
        if x == y:
            out.append(x)
        else:
            out.append(x * (1.0 - W) + y * W)
            changed += 1
    sub.set_face_model_coefficients(b, out)
    unreal.log("coeff blend applied (%d values changed, w=%.2f)" % (changed, W))
else:
    unreal.log("coeff arrays differ in length — SKIPPING blend")

sub.commit_face_state(b)
unreal.log("face state committed")
unreal.EditorLoadingAndSavingUtils.save_packages([b.get_package()], False)
unreal.log("BRI FIX SAVED")
