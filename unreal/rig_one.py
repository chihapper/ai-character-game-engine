"""Blocking auto-rig request for one character (set NAME). Full rig with blend shapes
for facial animation later (MetaHuman Animator drives blendshape-quality faces)."""
import unreal

sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
ch = unreal.EditorAssetLibrary.load_asset("/Game/Cast/%s" % NAME)
sub.try_add_object_to_edit(ch)

p = unreal.MetaHumanCharacterAutoRiggingRequestParams()
p.rig_type = unreal.MetaHumanRigType.JOINTS_AND_BLEND_SHAPES
p.blocking = False   # blocking=True asserts (SharedPointer IsValid) — async is the UI path
try:
    sub.request_auto_rigging(ch, p)
    unreal.log("%s RIG REQUESTED (async)" % NAME)
except Exception as e:
    unreal.log("%s RIG ERR: %s" % (NAME, e))
