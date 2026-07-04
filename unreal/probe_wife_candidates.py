"""Base-preset candidates for the wife's likeness: read tone/texture from the warm-skinned
female presets (incl. ones never previewed)."""
import unreal

for n in ["Sunita", "Asha", "Tuya", "Lani", "Etta", "Aoi", "Jelena", "Zuri"]:
    p = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Presets/%s" % n)
    if not p:
        unreal.log("%s: LOAD FAILED" % n)
        continue
    s = p.get_editor_property("skin_settings")
    unreal.log("%s: u=%.3f v=%.3f tex=%d" % (n, s.skin.u, s.skin.v, s.skin.face_texture_index))
