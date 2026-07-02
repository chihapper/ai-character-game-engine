// The cast with real bodies: Universal Base Characters (humanoid-rigged) + hairstyles parented
// to the head bone, driven by the baked UAL animator. Each character keeps the silhouette
// language the capsules established — build, height, hair, palette — now with limbs.
using System.Linq;
using UnityEngine;

public struct CastLook
{
    public bool feminine;
    public float height;      // uniform scale vs the base body
    public bool darkSkin;
    public string hair;       // FBX name under Hairstyles (or "")
    public bool beard;
    public string outfit;     // full outfit FBX under Q/Outfits (e.g. "Male_Peasant"), or ""
    public string[] outfitPieces;  // OR individual pieces (e.g. ranger without the hood)
    public Color outfitTint;
    public Color top, bottom, hairColor;
}

public static class CastBuilder
{
    const string BODY = "Q/Characters/Base Characters/Unity/";
    const string HAIR = "Q/Characters/Hairstyles/Rigged to Head Bone/FBX (Unity)/";
    const string CT = "Q/Characters/Base Characters/Textures/";

    public static GameObject Build(string name, Vector3 pos, CastLook look)
    {
        var prefab = Resources.Load<GameObject>(BODY + (look.feminine ? "Superhero_Female_FullBody" : "Superhero_Male_FullBody"));
        if (prefab == null) { Debug.LogError("CastBuilder: body prefab missing"); return new GameObject(name); }
        var body = Object.Instantiate(prefab, pos, prefab.transform.rotation);
        body.name = name;
        // normalize: the FBX's native height is whatever it is — measure it and scale so this
        // character stands look.height * 1.75m tall (playtest: bodies rendered ~half height and
        // the inn read as a canyon)
        var bb = new Bounds(pos, Vector3.zero); bool first = true;
        foreach (var r0 in body.GetComponentsInChildren<Renderer>())
        { if (first) { bb = r0.bounds; first = false; } else bb.Encapsulate(r0.bounds); }
        float measured = Mathf.Max(0.2f, bb.size.y);
        body.transform.localScale = Vector3.one * (look.height * 1.75f / measured);

        // animator: keep the imported humanoid avatar, drive with the baked controller
        var animator = body.GetComponent<Animator>() ?? body.AddComponent<Animator>();
        var ctrl = Resources.Load<RuntimeAnimatorController>("Q/NPCAnim");
        if (ctrl != null) animator.runtimeAnimatorController = ctrl;
        animator.applyRootMotion = false;

        // materials: base map first, then per-character overrides (skin variant, clothing tints)
        QMaterials.Apply(body);
        var skinTex = Resources.Load<Texture2D>(CT + (look.feminine
            ? (look.darkSkin ? "T_Superhero_Female_Dark_BaseColor" : "T_Superhero_Female_Light_BaseColor")
            : (look.darkSkin ? "T_Superhero_Male_Dark" : "T_Superhero_Male_Ligh")));
        foreach (var r in body.GetComponentsInChildren<Renderer>(true))
        {
            var mats = r.sharedMaterials;
            for (int i = 0; i < mats.Length; i++)
            {
                var nm = (mats[i]?.name ?? "").ToLower();
                if (nm.Contains("body_m") || nm.Contains("body_f"))
                { mats[i] = new Material(mats[i]); if (skinTex) mats[i].SetTexture("_BaseMap", skinTex); }
                else if (nm.Contains("topwear"))
                { mats[i] = new Material(mats[i]); mats[i].SetColor("_BaseColor", look.top); }
                else if (nm.Contains("bottomwear"))
                { mats[i] = new Material(mats[i]); mats[i].SetColor("_BaseColor", look.bottom); }
                else if (nm.Contains("hair") || nm.Contains("brow"))   // base-body eyebrows: pale texture reads WHITE untinted
                { mats[i] = new Material(mats[i]); mats[i].SetColor("_BaseColor", look.hairColor * 1.2f); }
            }
            r.sharedMaterials = mats;
        }

        // hair (+ beard) parented to the head bone, tinted per character
        var head = animator.isHuman ? animator.GetBoneTransform(HumanBodyBones.Head) : null;
        head ??= body.GetComponentsInChildren<Transform>().FirstOrDefault(t => t.name.ToLower().Contains("head"));
        void Attach(string fbx)
        {
            // rigged-to-head-bone hair: a skinned mesh bound to ONE bone — retarget that bone
            // to THIS body's head and it follows every nod for free
            var hp = Resources.Load<GameObject>(HAIR + fbx);
            if (hp == null || head == null)
            { Debug.LogWarning($"CastBuilder: hair attach failed {fbx} (prefab={(hp != null)} head={(head != null)})"); return; }
            var h = Object.Instantiate(hp, body.transform, false);
            h.transform.localPosition = Vector3.zero;
            h.transform.localRotation = hp.transform.rotation;   // keep the FBX axis compensation
            foreach (var smr in h.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                if (smr.bones.Length >= 1)
                {
                    var bones = smr.bones;
                    for (int i = 0; i < bones.Length; i++) bones[i] = head;
                    smr.bones = bones;
                    smr.rootBone = head;
                    smr.updateWhenOffscreen = true;
                }
                var m = new Material(QMaterials.Map("hair"));
                m.SetColor("_BaseColor", look.hairColor);
                smr.sharedMaterials = Enumerable.Repeat(m, smr.sharedMaterials.Length).ToArray();
            }
            foreach (var mr in h.GetComponentsInChildren<MeshRenderer>(true))
            {
                var m = new Material(QMaterials.Map("hair"));
                m.SetColor("_BaseColor", look.hairColor);
                mr.sharedMaterials = Enumerable.Repeat(m, mr.sharedMaterials.Length).ToArray();
            }
        }
        // the base body's own mesh, captured BEFORE outfit meshes join the hierarchy
        var baseBodySmr = body.GetComponentsInChildren<SkinnedMeshRenderer>(true)
            .Where(r => r.sharedMesh != null)
            .OrderByDescending(r => r.sharedMesh.vertexCount).FirstOrDefault();

        // OUTFIT: skinned to the same UBC skeleton — remap every bone by NAME onto this body
        var boneMap = body.GetComponentsInChildren<Transform>(true)
                          .GroupBy(t => t.name).ToDictionary(g => g.Key, g => g.First());
        void Dress(string fbx)
        {
            var op = Resources.Load<GameObject>("Q/Outfits/Exports/FBX (Unity)/Outfits/" + fbx)
                  ?? Resources.Load<GameObject>("Q/Outfits/Exports/FBX (Unity)/Modular Parts/" + fbx);
            if (op == null) { Debug.LogWarning("CastBuilder: outfit missing " + fbx); return; }
            var o = Object.Instantiate(op, body.transform, false);
            o.transform.localPosition = Vector3.zero;
            o.transform.localRotation = op.transform.rotation;   // keep the FBX axis compensation
            foreach (var smr in o.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                var bones = smr.bones;
                for (int i = 0; i < bones.Length; i++)
                    if (bones[i] != null && boneMap.TryGetValue(bones[i].name, out var mapped))
                        bones[i] = mapped;
                smr.bones = bones;
                if (smr.rootBone != null && boneMap.TryGetValue(smr.rootBone.name, out var rootM))
                    smr.rootBone = rootM;
                smr.updateWhenOffscreen = true;   // stale bind-bounds must not cull the clothes
                var mats = smr.sharedMaterials;
                for (int i = 0; i < mats.Length; i++)
                {
                    var m = new Material(QMaterials.Map(mats[i] ? mats[i].name : ""));
                    if (look.outfitTint.a > 0f)
                        m.SetColor("_BaseColor", m.GetColor("_BaseColor") * look.outfitTint);
                    mats[i] = m;
                }
                smr.sharedMaterials = mats;
            }
            // strip any duplicate armature transforms the outfit prefab brought along
            foreach (var t in o.GetComponentsInChildren<Transform>(true).Where(t => t != o.transform).ToArray())
                if (t != null && t.GetComponent<SkinnedMeshRenderer>() == null && t.childCount == 0
                    && t.GetComponentsInChildren<SkinnedMeshRenderer>(true).Length == 0)
                    Object.Destroy(t.gameObject);
        }
        bool dressed = !string.IsNullOrEmpty(look.outfit) || (look.outfitPieces != null && look.outfitPieces.Length > 0);
        if (!string.IsNullOrEmpty(look.outfit)) Dress(look.outfit);
        if (look.outfitPieces != null) foreach (var piece in look.outfitPieces) Dress(piece);
        if (dressed)
        {
            // the outfit REPLACES the body (pack readme: full body under clothes = clipping):
            // swap the base mesh for its baked head-only variant — same skeleton, same materials
            var headMesh = Resources.Load<Mesh>("Q/" + (look.feminine ? "HeadOnly_Female" : "HeadOnly_Male"));
            if (headMesh != null && baseBodySmr != null)
                baseBodySmr.sharedMesh = headMesh;
        }

        if (!string.IsNullOrEmpty(look.hair)) Attach(look.hair);
        if (look.beard) Attach("Hair_Beard");
        // no eyebrow attach: the base body ships its own Eyebrows/Eyes meshes

        // one capsule collider on the root carries line of sight
        var col = body.AddComponent<CapsuleCollider>();
        col.height = 1.8f * look.height;
        col.center = new Vector3(0, 0.9f * look.height, 0);
        col.radius = 0.3f;
        return body;
    }
}
