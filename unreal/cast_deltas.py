"""Light per-character deltas on top of the preset base. Toolkit opened per char.
Della: harder age tells (teeth, gray lashes). Bri: subtle makeup + green eyes.
Corvin/Edwin: preset stands as-is."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
aes = unreal.get_editor_subsystem(unreal.AssetEditorSubsystem)

def with_char(name, fn):
    path = "/Game/Cast/%s" % name
    ch = unreal.EditorAssetLibrary.load_asset(path)
    sub.try_add_object_to_edit(ch)
    try:
        fn(ch)
        unreal.EditorAssetLibrary.save_asset(path)
        unreal.log("%s deltas OK" % name)
    except Exception as e:
        unreal.log("%s deltas ERR: %s" % (name, e))

def della(ch):
    h = ch.get_editor_property("head_model_settings")
    h.teeth.worn_down = 0.6
    h.teeth.receding_gums = 0.4
    h.eyelashes.salt_and_pepper = 0.9
    h.eyelashes.lightness = 0.7
    sub.commit_head_model_settings(ch, h)

def bri(ch):
    m = ch.get_editor_property("makeup_settings")
    m.foundation.apply_foundation = True
    m.foundation.intensity = 0.3
    m.foundation.concealer = 0.6
    sub.commit_makeup_settings(ch, m)
    e = ch.get_editor_property("eyes_settings")
    e.eye_left.iris.primary_color_u = 0.35
    e.eye_left.iris.primary_color_v = 0.62
    e.eye_right.iris.primary_color_u = 0.35
    e.eye_right.iris.primary_color_v = 0.62
    sub.commit_eyes_settings(ch, e)

with_char("MH_Della", della)
with_char("MH_Bri", bri)
unreal.log("DELTAS DONE")
