// One-shot bake (headless: -executeMethod QBake.Bake): builds the NPC AnimatorController from
// whatever clips the Universal Animation Libraries actually contain (matched by name, logged in
// full so the mapping can be refined against reality), and writes an asset inventory report.
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

public static class QBake
{
    public static void Bake()
    {
        var clips = new[] { "Assets/Resources/Q/Anims/Unity/UAL1_Standard.fbx",
                            "Assets/Resources/Q/Anims2/Unity/UAL2_Standard.fbx" }
            .SelectMany(p => AssetDatabase.LoadAllAssetsAtPath(p).OfType<AnimationClip>())
            .Where(c => !c.name.StartsWith("__preview"))
            .ToList();
        Debug.Log($"QBAKE CLIP INVENTORY ({clips.Count}):\n" + string.Join("\n", clips.Select(c => c.name)));

        AnimationClip Exact(string key) => clips.FirstOrDefault(c => c.name == "Armature|" + key);

        var idle = Exact("Idle_Loop");
        var walk = Exact("Walk_Loop");
        var sit = Exact("Sitting_Idle_Loop");
        var talk = Exact("Idle_Talking_Loop");
        var lean = Exact("Idle_Rail_Loop");      // the bar-lean
        var arms = Exact("Idle_FoldArms_Loop");  // watchful, arms crossed
        Debug.Log($"QBAKE MAP idle={idle?.name} walk={walk?.name} sit={sit?.name} talk={talk?.name} lean={lean?.name} arms={arms?.name}");

        var ctrl = AnimatorController.CreateAnimatorControllerAtPath("Assets/Resources/Q/NPCAnim.controller");
        ctrl.AddParameter("Speed", AnimatorControllerParameterType.Float);
        foreach (var b in new[] { "Sit", "Talk", "Lean", "Arms" })
            ctrl.AddParameter(b, AnimatorControllerParameterType.Bool);
        var sm = ctrl.layers[0].stateMachine;

        var move = sm.AddState("Move");
        var tree = new BlendTree { name = "MoveTree", blendParameter = "Speed", useAutomaticThresholds = false };
        AssetDatabase.AddObjectToAsset(tree, ctrl);
        if (idle != null) tree.AddChild(idle, 0f);
        if (walk != null) tree.AddChild(walk, 1f);   // Speed is NORMALIZED 0..1 (glide fix)
        move.motion = tree;
        sm.defaultState = move;

        void BoolState(string flag, AnimationClip clip)
        {
            if (clip == null) return;
            var st = sm.AddState(flag); st.motion = clip;
            var to = move.AddTransition(st); to.AddCondition(AnimatorConditionMode.If, 0, flag); to.hasExitTime = false; to.duration = 0.3f;
            var back = st.AddTransition(move); back.AddCondition(AnimatorConditionMode.IfNot, 0, flag); back.hasExitTime = false; back.duration = 0.3f;
        }
        BoolState("Sit", sit);
        BoolState("Talk", talk);
        BoolState("Lean", lean);
        BoolState("Arms", arms);
        AssetDatabase.SaveAssets();
        Debug.Log("QBAKE controller saved");

        foreach (var p in new[] { "Assets/Resources/Q/Characters/Base Characters/Unity/Superhero_Male_FullBody.fbx",
                                  "Assets/Resources/Q/Characters/Base Characters/Unity/Superhero_Female_FullBody.fbx" })
        {
            var go = AssetDatabase.LoadAssetAtPath<GameObject>(p);
            var av = go ? go.GetComponent<Animator>()?.avatar : null;
            Debug.Log($"QBAKE body {p.Split('/').Last()} humanoidAvatar={(av != null && av.isHuman)}");
        }
        Debug.Log("QBAKE DONE");
    }
}
