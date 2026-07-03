"""What texture machinery exists? commit_skin_settings asserted on BodyTexture with
index 4 — find the valid index range / synthesis path before committing again."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
tex_methods = [m for m in dir(sub) if not m.startswith("_") and ("tex" in m.lower() or "synth" in m.lower() or "skin" in m.lower() or "body" in m.lower())]
unreal.log("SUB TEX METHODS: %s" % ", ".join(tex_methods))

for m in tex_methods:
    try:
        unreal.log("  %s :: %s" % (m, (getattr(sub, m).__doc__ or "").split("\n")[0][:160]))
    except Exception:
        pass

# classes that sound texture-related
names = [n for n in dir(unreal) if "metahuman" in n.lower() and ("tex" in n.lower() or "skin" in n.lower() or "body" in n.lower())]
unreal.log("TEX CLASSES: %s" % ", ".join(names))

d = unreal.EditorAssetLibrary.load_asset("/Game/Cast/MH_Della")
if d:
    unreal.log("has_high_res: %s" % d.has_high_resolution_textures)
    bt = d.get_editor_property("body_textures")
    unreal.log("body_textures type=%s len-ish=%s" % (type(bt).__name__, str(bt)[:300]))
    sft = d.get_editor_property("synthesized_face_textures")
    unreal.log("synth_face_textures: %s" % str(sft)[:300])
