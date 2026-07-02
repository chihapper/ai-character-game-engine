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

        AnimationClip Find(params string[] keys) =>
            keys.Select(k => clips.FirstOrDefault(c => c.name.ToLower().Contains(k.ToLower())))
                .FirstOrDefault(c => c != null);

        var idle = Find("Idle_A", "Idle");
        var walk = Find("Walking_A", "Walk_A", "Walk");
        var sit = Find("Sit_Chair_Idle", "Sit_Floor_Idle", "Sitting", "Sit");
        var talk = Find("Talking", "Talk", "Interact");
        Debug.Log($"QBAKE MAP idle={idle?.name} walk={walk?.name} sit={sit?.name} talk={talk?.name}");

        var ctrl = AnimatorController.CreateAnimatorControllerAtPath("Assets/Resources/Q/NPCAnim.controller");
        ctrl.AddParameter("Speed", AnimatorControllerParameterType.Float);
        ctrl.AddParameter("Sit", AnimatorControllerParameterType.Bool);
        ctrl.AddParameter("Talk", AnimatorControllerParameterType.Bool);
        var sm = ctrl.layers[0].stateMachine;

        var move = sm.AddState("Move");
        var tree = new BlendTree { name = "MoveTree", blendParameter = "Speed", useAutomaticThresholds = false };
        AssetDatabase.AddObjectToAsset(tree, ctrl);
        if (idle != null) tree.AddChild(idle, 0f);
        if (walk != null) tree.AddChild(walk, 1.6f);
        move.motion = tree;
        sm.defaultState = move;

        if (sit != null)
        {
            var s = sm.AddState("Sit"); s.motion = sit;
            var to = move.AddTransition(s); to.AddCondition(AnimatorConditionMode.If, 0, "Sit"); to.hasExitTime = false; to.duration = 0.25f;
            var back = s.AddTransition(move); back.AddCondition(AnimatorConditionMode.IfNot, 0, "Sit"); back.hasExitTime = false; back.duration = 0.25f;
        }
        if (talk != null)
        {
            var t = sm.AddState("Talk"); t.motion = talk;
            var to = move.AddTransition(t); to.AddCondition(AnimatorConditionMode.If, 0, "Talk"); to.AddCondition(AnimatorConditionMode.Less, 0.1f, "Speed"); to.hasExitTime = false; to.duration = 0.3f;
            var back = t.AddTransition(move); back.AddCondition(AnimatorConditionMode.IfNot, 0, "Talk"); back.hasExitTime = false; back.duration = 0.3f;
        }
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
