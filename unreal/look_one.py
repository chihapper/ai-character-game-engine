"""Apply one character's look. Set NAME before exec. Toolkit for that character must be open.
body_texture_index stays 0 ALWAYS — nonzero asserts (cloud-download-only textures)."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)

LOOKS = {
    "MH_Della": dict(face_tex=4, rough=1.4, tone=(0.62, 0.55),
                     teeth=dict(worn_down=0.75, receding_gums=0.55, upper_shift=0.2),
                     lashes=dict(salt_and_pepper=0.95, lightness=0.75)),
    "MH_Corvin": dict(face_tex=3, rough=1.25, tone=(0.55, 0.52),
                      teeth=dict(worn_down=0.3)),
    "MH_Edwin": dict(face_tex=1, rough=1.0, tone=(0.5, 0.5)),
    "MH_Bri": dict(face_tex=0, rough=0.85, tone=(0.45, 0.48),
                   makeup=True, iris=(0.35, 0.62)),
}

cfg = LOOKS[NAME]
path = "/Game/Cast/%s" % NAME
ch = unreal.EditorAssetLibrary.load_asset(path)

s = ch.get_editor_property("skin_settings")
s.skin.face_texture_index = cfg["face_tex"]
s.skin.body_texture_index = 0
s.skin.roughness = cfg["rough"]
s.skin.u, s.skin.v = cfg["tone"]
sub.commit_skin_settings(ch, s)
unreal.log("%s skin committed (face_tex=%s)" % (NAME, cfg["face_tex"]))

if "teeth" in cfg or "lashes" in cfg:
    h = ch.get_editor_property("head_model_settings")
    for k, v in cfg.get("teeth", {}).items():
        setattr(h.teeth, k, v)
    for k, v in cfg.get("lashes", {}).items():
        setattr(h.eyelashes, k, v)
    sub.commit_head_model_settings(ch, h)
    unreal.log("%s head model committed" % NAME)

if cfg.get("makeup"):
    m = ch.get_editor_property("makeup_settings")
    m.foundation.apply_foundation = True
    m.foundation.intensity = 0.35
    m.foundation.concealer = 0.7
    sub.commit_makeup_settings(ch, m)
    unreal.log("%s makeup committed" % NAME)

if "iris" in cfg:
    e = ch.get_editor_property("eyes_settings")
    e.eye_left.iris.primary_color_u, e.eye_left.iris.primary_color_v = cfg["iris"]
    e.eye_right.iris.primary_color_u, e.eye_right.iris.primary_color_v = cfg["iris"]
    sub.commit_eyes_settings(ch, e)
    unreal.log("%s eyes committed" % NAME)

unreal.EditorAssetLibrary.save_asset(path)
unreal.log("%s LOOK SAVED" % NAME)
