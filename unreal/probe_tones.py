"""Map the skin tone chart: read u/v from presets whose complexions we've seen."""
import unreal

for n in ["Vivian", "Celeste", "Aera", "Jelena", "Zuri", "Ada", "Sook-ja", "Bruce", "Orlando", "Etta"]:
    p = unreal.EditorAssetLibrary.load_asset("/MetaHumanCharacter/Optional/Presets/%s" % n)
    if not p:
        unreal.log("%s: LOAD FAILED" % n)
        continue
    s = p.get_editor_property("skin_settings")
    unreal.log("%s: u=%.3f v=%.3f tex=%d" % (n, s.skin.u, s.skin.v, s.skin.face_texture_index))
