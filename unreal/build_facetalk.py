"""FaceTalk: duplicate the neutral face idle and lay syllabic jaw/lip curves over it.
Runs through the same rig-logic path as the (working) expression loops."""
import math
import unreal

eal = unreal.EditorAssetLibrary

# exact curve names, from a face loop that works
surp = eal.load_asset("/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Expression_Loops/SurpriseA/mhc_mh002_fmn_f_facialloop_surprise_f_s001")
names = [str(n) for n in unreal.AnimationLibrary.get_animation_curve_names(surp, unreal.RawCurveTrackTypes.RCT_FLOAT)]
mouthy = [n for n in names if any(k in n.lower() for k in ("jaw", "mouth", "lip"))]
unreal.log("mouth-family curves available: %s" % mouthy)

def pick(*frags):
    for n in names:
        if all(f in n.lower() for f in frags):
            return n
    return None

JAW   = pick("jawopen") or pick("jaw", "open")
UP_L  = pick("mouthupperlipraisel") or pick("upperlipraise", "l")
UP_R  = pick("mouthupperlipraiser") or pick("upperlipraise", "r")
DN_L  = pick("mouthlowerlipdepressl") or pick("lowerlipdepress", "l")
DN_R  = pick("mouthlowerlipdepressr") or pick("lowerlipdepress", "r")
CRN_L = pick("mouthcornerpulll")
CRN_R = pick("mouthcornerpullr")
unreal.log("picked: jaw=%s upL=%s dnL=%s crnL=%s" % (JAW, UP_L, DN_L, CRN_L))

SRC = "/MetaHumanCharacter/Optional/Animation/TemplateAnimations/Technical_Loops/Idle/mhc_mh001_fmn_f_idle"
DST_DIR = "/Game/Cast/Anims/MH"
DST = DST_DIR + "/FaceTalk"
if eal.does_asset_exist(DST):
    eal.delete_asset(DST)
dup = eal.duplicate_asset(SRC, DST)
if not dup:
    raise RuntimeError("duplicate failed")
length = dup.get_play_length()
unreal.log("FaceTalk base duplicated, length %.2fs" % length)

def lay(curve, times, values):
    if not curve:
        return
    cname = curve  # exact name string
    try:
        unreal.AnimationLibrary.remove_curve(dup, cname)
    except Exception:
        pass
    unreal.AnimationLibrary.add_curve(dup, cname)
    unreal.AnimationLibrary.add_float_curve_keys(dup, cname, times, values)

STEP = 0.06
times, jaw_v, up_v, dn_v, crn_v = [], [], [], [], []
t = 0.0
while t <= length:
    times.append(t)
    # syllables ~5 Hz with phrase-level swell; two incommensurate sines = non-repeating feel
    syl = max(0.0, math.sin(t * 10.5) * 0.6 + math.sin(t * 6.1) * 0.4)
    phrase = 0.6 + 0.4 * math.sin(t * 1.7 + 1.0)
    j = min(0.5, 0.08 + 0.42 * syl * phrase)
    jaw_v.append(j)
    up_v.append(j * 0.30)
    dn_v.append(j * 0.45)
    crn_v.append(0.04 + 0.05 * math.sin(t * 2.3))   # faint animation at the corners, not a grin
    t += STEP

lay(JAW, times, jaw_v)
lay(UP_L, times, up_v)
lay(UP_R, times, up_v)
lay(DN_L, times, dn_v)
lay(DN_R, times, dn_v)
lay(CRN_L, times, crn_v)
lay(CRN_R, times, crn_v)

ok = eal.save_asset(DST)
unreal.log("FaceTalk saved: %s (curves on %d keys)" % (ok, len(times)))
