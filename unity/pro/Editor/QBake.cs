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
        var jog = Exact("Jog_Fwd_Loop");         // urgent crossings
        var sit = Exact("Sitting_Idle_Loop");
        var sitEnter = Exact("Sitting_Enter");   // a body settles ONTO the seat, no more teleport-sit
        var sitExit = Exact("Sitting_Exit");
        var sitTalk = Exact("Sitting_Talking_Loop");
        var talk = Exact("Idle_Talking_Loop");
        var lean = Exact("Idle_Rail_Loop");      // the bar-lean
        var leanCall = Exact("Idle_Rail_Call");  // calling out WHILE leaning
        var arms = Exact("Idle_FoldArms_Loop");  // watchful, arms crossed
        var consume = Exact("Consume");          // a sip from the cup
        var nod = Exact("Yes");
        var shake = Exact("Idle_No_Loop");
        Debug.Log($"QBAKE MAP idle={idle?.name} walk={walk?.name} jog={jog?.name} sit={sit?.name} " +
                  $"enter={sitEnter?.name} exit={sitExit?.name} sitTalk={sitTalk?.name} talk={talk?.name} " +
                  $"lean={lean?.name} call={leanCall?.name} arms={arms?.name} sip={consume?.name} nod={nod?.name} shake={shake?.name}");

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
        if (jog != null) tree.AddChild(jog, 2f);     // Speed 2 = hurrying
        move.motion = tree;
        sm.defaultState = move;

        AnimatorState BoolState(string flag, AnimationClip clip)
        {
            if (clip == null) return null;
            var st = sm.AddState(flag); st.motion = clip;
            var to = move.AddTransition(st); to.AddCondition(AnimatorConditionMode.If, 0, flag); to.hasExitTime = false; to.duration = 0.3f;
            var back = st.AddTransition(move); back.AddCondition(AnimatorConditionMode.IfNot, 0, flag); back.hasExitTime = false; back.duration = 0.3f;
            return st;
        }

        // SIT is a journey, not a flag: Move -> Sitting_Enter -> Sit ... Sit -> Sitting_Exit -> Move,
        // with Sitting_Talking while seated and Talk raised
        AnimatorState sitState = null;
        if (sit != null)
        {
            sitState = sm.AddState("Sit"); sitState.motion = sit;
            if (sitEnter != null)
            {
                var enterSt = sm.AddState("SitEnter"); enterSt.motion = sitEnter;
                var t1 = move.AddTransition(enterSt); t1.AddCondition(AnimatorConditionMode.If, 0, "Sit"); t1.hasExitTime = false; t1.duration = 0.15f;
                var t2 = enterSt.AddTransition(sitState); t2.hasExitTime = true; t2.exitTime = 0.9f; t2.duration = 0.1f;
            }
            else
            { var t = move.AddTransition(sitState); t.AddCondition(AnimatorConditionMode.If, 0, "Sit"); t.hasExitTime = false; t.duration = 0.3f; }
            if (sitExit != null)
            {
                var exitSt = sm.AddState("SitExit"); exitSt.motion = sitExit;
                var t3 = sitState.AddTransition(exitSt); t3.AddCondition(AnimatorConditionMode.IfNot, 0, "Sit"); t3.hasExitTime = false; t3.duration = 0.1f;
                var t4 = exitSt.AddTransition(move); t4.hasExitTime = true; t4.exitTime = 0.85f; t4.duration = 0.15f;
            }
            else
            { var t = sitState.AddTransition(move); t.AddCondition(AnimatorConditionMode.IfNot, 0, "Sit"); t.hasExitTime = false; t.duration = 0.3f; }
            if (sitTalk != null)
            {
                var st = sm.AddState("SitTalk"); st.motion = sitTalk;
                var a = sitState.AddTransition(st); a.AddCondition(AnimatorConditionMode.If, 0, "Talk"); a.hasExitTime = false; a.duration = 0.25f;
                var b = st.AddTransition(sitState); b.AddCondition(AnimatorConditionMode.IfNot, 0, "Talk"); b.hasExitTime = false; b.duration = 0.25f;
            }
        }

        BoolState("Talk", talk);
        var leanState = BoolState("Lean", lean);
        BoolState("Arms", arms);
        if (leanState != null && leanCall != null)
        {
            // Corvin hails you without leaving his wall
            var lc = sm.AddState("LeanTalk"); lc.motion = leanCall;
            var a = leanState.AddTransition(lc); a.AddCondition(AnimatorConditionMode.If, 0, "Talk"); a.hasExitTime = false; a.duration = 0.25f;
            var b = lc.AddTransition(leanState); b.AddCondition(AnimatorConditionMode.IfNot, 0, "Talk"); b.hasExitTime = false; b.duration = 0.25f;
        }

        // one-shot gestures, playable from idle, seated, or leaning — return to wherever the
        // body still belongs (conditional returns are evaluated before the unconditional one)
        void OneShot(string trig, AnimationClip clip)
        {
            if (clip == null) return;
            ctrl.AddParameter(trig, AnimatorControllerParameterType.Trigger);
            var st = sm.AddState(trig); st.motion = clip;
            foreach (var f in new[] { move, sitState, leanState })
            {
                if (f == null) continue;
                var t = f.AddTransition(st); t.AddCondition(AnimatorConditionMode.If, 0, trig); t.hasExitTime = false; t.duration = 0.15f;
            }
            if (sitState != null)
            { var r = st.AddTransition(sitState); r.AddCondition(AnimatorConditionMode.If, 0, "Sit"); r.hasExitTime = true; r.exitTime = 0.92f; r.duration = 0.2f; }
            if (leanState != null)
            { var r = st.AddTransition(leanState); r.AddCondition(AnimatorConditionMode.If, 0, "Lean"); r.hasExitTime = true; r.exitTime = 0.92f; r.duration = 0.2f; }
            var rm = st.AddTransition(move); rm.hasExitTime = true; rm.exitTime = 0.95f; rm.duration = 0.2f;
        }
        OneShot("Sip", consume);
        OneShot("Nod", nod);
        OneShot("Shake", shake);
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
