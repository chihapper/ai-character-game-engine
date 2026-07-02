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
    public Color top, bottom, hairColor;
}

public static class CastBuilder
{
    const string BODY = "Q/Characters/Base Characters/Unity/";
    const string HAIR = "Q/Characters/Hairstyles/Origin at 0/FBX (Unity)/";
    const string CT = "Q/Characters/Base Characters/Textures/";

    public static GameObject Build(string name, Vector3 pos, CastLook look)
    {
        var prefab = Resources.Load<GameObject>(BODY + (look.feminine ? "Superhero_Female_FullBody" : "Superhero_Male_FullBody"));
        if (prefab == null) { Debug.LogError("CastBuilder: body prefab missing"); return new GameObject(name); }
        var body = Object.Instantiate(prefab, pos, Quaternion.identity);
        body.name = name;
        body.transform.localScale = Vector3.one * look.height;

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
            }
            r.sharedMaterials = mats;
        }

        // hair (+ beard) parented to the head bone, tinted per character
        var head = animator.isHuman ? animator.GetBoneTransform(HumanBodyBones.Head) : null;
        head ??= body.GetComponentsInChildren<Transform>().FirstOrDefault(t => t.name.ToLower().Contains("head"));
        void Attach(string fbx)
        {
            var hp = Resources.Load<GameObject>(HAIR + fbx);
            if (hp == null || head == null) return;
            var h = Object.Instantiate(hp, head, false);
            h.transform.localPosition = Vector3.zero;
            h.transform.localRotation = Quaternion.identity;
            foreach (var r in h.GetComponentsInChildren<Renderer>(true))
            {
                var m = new Material(QMaterials.Map("hair"));
                m.SetColor("_BaseColor", look.hairColor);
                r.sharedMaterials = Enumerable.Repeat(m, r.sharedMaterials.Length).ToArray();
            }
        }
        if (!string.IsNullOrEmpty(look.hair)) Attach(look.hair);
        if (look.beard) Attach("Hair_Beard");
        Attach(look.feminine ? "Eyebrows_Female" : "Eyebrows_Regular");

        // one capsule collider on the root carries line of sight
        var col = body.AddComponent<CapsuleCollider>();
        col.height = 1.8f * look.height;
        col.center = new Vector3(0, 0.9f * look.height, 0);
        col.radius = 0.3f;
        return body;
    }
}
