"""Casting step 3: the look passes. Semantic parameters per the user's brief —
Della aged hard by the river, Corvin all edges, Edwin open-faced, Bri young and striking.
Geometry sculpting stays with the user; these are the levers the API exposes cleanly."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)

def look(name, tweak):
    path = "/Game/Cast/%s" % name
    ch = unreal.EditorAssetLibrary.load_asset(path)
    if not ch:
        unreal.log("%s: MISSING" % name)
        return
    sub.try_add_object_to_edit(ch)
    try:
        tweak(ch)
        unreal.EditorAssetLibrary.save_asset(path)
        unreal.log("%s: look applied + saved" % name)
    except Exception as e:
        unreal.log("%s: ERR %s" % (name, e))

def della(ch):
    s = ch.get_editor_property("skin_settings")
    s.skin.face_texture_index = 4      # older texture sets live at higher indices (verify by eye)
    s.skin.body_texture_index = 4
    s.skin.roughness = 1.4             # weathered, matte
    sub.commit_skin_settings(ch, s)    # asset props are read-only; the subsystem is the write path
    h = ch.get_editor_property("head_model_settings")
    h.teeth.worn_down = 0.75           # a life of river weather and pipe smoke
    h.teeth.receding_gums = 0.55
    h.teeth.upper_shift = 0.2
    h.eyelashes.salt_and_pepper = 0.95
    h.eyelashes.lightness = 0.75       # gone gray
    sub.commit_head_model_settings(ch, h)

def corvin(ch):
    s = ch.get_editor_property("skin_settings")
    s.skin.face_texture_index = 3      # lined, hard
    s.skin.body_texture_index = 3
    s.skin.roughness = 1.25
    sub.commit_skin_settings(ch, s)
    h = ch.get_editor_property("head_model_settings")
    h.teeth.worn_down = 0.3
    sub.commit_head_model_settings(ch, h)

def edwin(ch):
    s = ch.get_editor_property("skin_settings")
    s.skin.face_texture_index = 1      # mid-thirties, expressive
    s.skin.roughness = 1.0
    sub.commit_skin_settings(ch, s)

def bri(ch):
    s = ch.get_editor_property("skin_settings")
    s.skin.face_texture_index = 0      # youngest, smoothest set
    s.skin.body_texture_index = 0
    s.skin.roughness = 0.85            # a touch of glow
    sub.commit_skin_settings(ch, s)
    m = ch.get_editor_property("makeup_settings")
    m.foundation.apply_foundation = True
    m.foundation.intensity = 0.35
    m.foundation.concealer = 0.7
    sub.commit_makeup_settings(ch, m)
    e = ch.get_editor_property("eyes_settings")
    e.eye_left.iris.primary_color_u = 0.35   # toward a striking green
    e.eye_left.iris.primary_color_v = 0.62
    e.eye_right.iris.primary_color_u = 0.35
    e.eye_right.iris.primary_color_v = 0.62
    sub.commit_eyes_settings(ch, e)

look("MH_Della", della)
look("MH_Corvin", corvin)
look("MH_Edwin", edwin)
look("MH_Bri", bri)
unreal.log("CAST LOOKS DONE")
