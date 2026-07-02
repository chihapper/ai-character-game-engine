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
        BakeHeadOnly("Assets/Resources/Q/Characters/Base Characters/Unity/Superhero_Male_FullBody.fbx", "HeadOnly_Male");
        BakeHeadOnly("Assets/Resources/Q/Characters/Base Characters/Unity/Superhero_Female_FullBody.fbx", "HeadOnly_Female");
        AssetDatabase.SaveAssets();
        Debug.Log("QBAKE DONE");
    }

    /// The outfit pack's readme: "only the head of the model is required — using the full body
    /// will result in clipping." The outfits REPLACE the body. This bakes a head-only variant of
    /// each base mesh (keep triangles fully weighted to head/neck/eye bones, drop the rest;
    /// vertices/bindposes/submeshes untouched so materials and skinning stay valid).
    static void BakeHeadOnly(string path, string outName)
    {
        var go = AssetDatabase.LoadAssetAtPath<GameObject>(path);
        if (go == null) { Debug.Log("QBAKE headonly: missing " + path); return; }
        var smr = go.GetComponentsInChildren<SkinnedMeshRenderer>(true)
                    .OrderByDescending(r => r.sharedMesh != null ? r.sharedMesh.vertexCount : 0).First();
        var mesh = smr.sharedMesh;
        var keepBone = new System.Collections.Generic.HashSet<int>();
        for (int i = 0; i < smr.bones.Length; i++)
        {
            var n = smr.bones[i] != null ? smr.bones[i].name.ToLower() : "";
            if (n.Contains("head") || n.Contains("neck") || n.Contains("eye") || n.Contains("jaw"))
                keepBone.Add(i);
        }
        var bw = mesh.boneWeights;
        float HeadW(int v)
        {
            var w = bw[v]; float t = 0;
            if (keepBone.Contains(w.boneIndex0)) t += w.weight0;
            if (keepBone.Contains(w.boneIndex1)) t += w.weight1;
            if (keepBone.Contains(w.boneIndex2)) t += w.weight2;
            if (keepBone.Contains(w.boneIndex3)) t += w.weight3;
            return t;
        }
        var outMesh = UnityEngine.Object.Instantiate(mesh);
        outMesh.name = outName;
        for (int sub = 0; sub < mesh.subMeshCount; sub++)
        {
            var tris = mesh.GetTriangles(sub);
            var kept = new System.Collections.Generic.List<int>(tris.Length);
            for (int t = 0; t < tris.Length; t += 3)
                if (HeadW(tris[t]) > 0.35f && HeadW(tris[t + 1]) > 0.35f && HeadW(tris[t + 2]) > 0.35f)
                { kept.Add(tris[t]); kept.Add(tris[t + 1]); kept.Add(tris[t + 2]); }
            outMesh.SetTriangles(kept, sub);
        }
        AssetDatabase.CreateAsset(outMesh, "Assets/Resources/Q/" + outName + ".asset");
        Debug.Log($"QBAKE headonly {outName}: {mesh.triangles.Length / 3} -> {outMesh.triangles.Length / 3} tris");
    }
}
