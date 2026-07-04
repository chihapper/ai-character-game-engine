"""Which presets share Sunita's coefficient structure? Compare the leading values (structure/
header) — if those differ, cross-blending corrupts geometry (the Tuya chin incident)."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
su = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Presets/Sunita")
sub.try_add_object_to_edit(su)
sa = list(sub.get_face_model_coefficients(su))
unreal.log("Sunita header: %s" % [round(x, 3) for x in sa[:10]])

for n in ["Tuya", "Asha", "Etta", "Lani", "Jelena", "Zuri", "Vivian", "Aera", "Celeste", "Ada", "Aoi", "Grace"]:
    p = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Presets/%s" % n)
    sub.try_add_object_to_edit(p)
    pa = list(sub.get_face_model_coefficients(p))
    if len(pa) != len(sa):
        unreal.log("%s: LEN MISMATCH (%d)" % (n, len(pa)))
        continue
    hdr = all(pa[i] == sa[i] for i in range(10))
    diffs = sum(1 for x, y in zip(sa, pa) if x != y)
    unreal.log("%s: header_match=%s, %d/%d values differ | hdr=%s" % (n, hdr, diffs, len(sa), [round(x, 3) for x in pa[:10]]))
