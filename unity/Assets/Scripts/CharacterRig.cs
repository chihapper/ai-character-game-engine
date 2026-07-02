// Procedural bodies from primitives — no models, no assets, but each figure reads as WHO they
// are: gender proportions, height, hair, clothing palette, and a signature prop (apron / hood /
// performer's hat / neat cloak). One capsule collider on the root serves line-of-sight; the
// visual parts carry no physics.
using UnityEngine;

public enum Hair { Bun, Ponytail, Short, Hooded }
public enum Prop { None, Apron, Hood, Hat, Cloak }

public struct RigSpec
{
    public bool feminine;      // narrower shoulders, wider hips, slighter build
    public float height;       // ~1.6-1.85
    public Color skin, hairC, top, bottom, propC;
    public Hair hair;
    public Prop prop;
}

public static class CharacterRig
{
    public static GameObject Build(string name, Vector3 groundPos, RigSpec s)
    {
        var root = new GameObject(name);
        root.transform.position = groundPos;
        float h = s.height / 1.75f;                      // proportion scale
        float shoulders = (s.feminine ? 0.30f : 0.38f) * h;
        float hips = (s.feminine ? 0.30f : 0.26f) * h;
        float legH = 0.82f * h, torsoH = 0.62f * h;

        // legs
        Part(root, PrimitiveType.Capsule, new Vector3(-hips / 3, legH / 2, 0),
             new Vector3(0.16f * h, legH / 2, 0.16f * h), s.bottom);
        Part(root, PrimitiveType.Capsule, new Vector3(hips / 3, legH / 2, 0),
             new Vector3(0.16f * h, legH / 2, 0.16f * h), s.bottom);
        // torso
        Part(root, PrimitiveType.Capsule, new Vector3(0, legH + torsoH / 2, 0),
             new Vector3(shoulders, torsoH / 2 + 0.06f, 0.24f * h), s.top);
        // arms
        Part(root, PrimitiveType.Capsule, new Vector3(-shoulders / 2 - 0.06f * h, legH + torsoH / 2, 0),
             new Vector3(0.10f * h, torsoH / 2, 0.10f * h), s.top);
        Part(root, PrimitiveType.Capsule, new Vector3(shoulders / 2 + 0.06f * h, legH + torsoH / 2, 0),
             new Vector3(0.10f * h, torsoH / 2, 0.10f * h), s.top);
        // head
        float headY = legH + torsoH + 0.13f * h;
        Part(root, PrimitiveType.Sphere, new Vector3(0, headY, 0),
             Vector3.one * 0.27f * h, s.skin);

        switch (s.hair)
        {
            case Hair.Bun:
                Part(root, PrimitiveType.Sphere, new Vector3(0, headY + 0.10f * h, 0),
                     new Vector3(0.26f, 0.14f, 0.26f) * h, s.hairC);
                Part(root, PrimitiveType.Sphere, new Vector3(0, headY + 0.13f * h, -0.10f * h),
                     Vector3.one * 0.12f * h, s.hairC);
                break;
            case Hair.Ponytail:
                Part(root, PrimitiveType.Sphere, new Vector3(0, headY + 0.10f * h, 0),
                     new Vector3(0.26f, 0.14f, 0.26f) * h, s.hairC);
                Part(root, PrimitiveType.Capsule, new Vector3(0, headY - 0.05f * h, -0.16f * h),
                     new Vector3(0.07f, 0.16f, 0.07f) * h, s.hairC);
                break;
            case Hair.Short:
                Part(root, PrimitiveType.Sphere, new Vector3(0, headY + 0.09f * h, -0.02f * h),
                     new Vector3(0.27f, 0.15f, 0.27f) * h, s.hairC);
                break;
            case Hair.Hooded:
                Part(root, PrimitiveType.Sphere, new Vector3(0, headY + 0.03f * h, -0.04f * h),
                     Vector3.one * 0.34f * h, s.propC);   // the hood swallows the head's outline
                break;
        }

        switch (s.prop)
        {
            case Prop.Apron:
                Part(root, PrimitiveType.Cube, new Vector3(0, legH + torsoH * 0.35f, 0.14f * h),
                     new Vector3(shoulders * 0.9f, torsoH * 0.9f, 0.02f), s.propC);
                break;
            case Prop.Hood:  // a long dark cloak falling from the shoulders
                Part(root, PrimitiveType.Capsule, new Vector3(0, legH * 0.75f + torsoH / 2, -0.08f * h),
                     new Vector3(shoulders * 1.25f, torsoH / 2 + legH * 0.28f, 0.22f * h), s.propC);
                break;
            case Prop.Hat:   // a performer's brimmed hat
                Part(root, PrimitiveType.Cylinder, new Vector3(0, headY + 0.13f * h, 0),
                     new Vector3(0.36f * h, 0.01f, 0.36f * h), s.propC);
                Part(root, PrimitiveType.Cylinder, new Vector3(0, headY + 0.19f * h, 0),
                     new Vector3(0.18f * h, 0.07f * h, 0.18f * h), s.propC);
                break;
            case Prop.Cloak: // a neat traveling cloak, worn squared
                Part(root, PrimitiveType.Capsule, new Vector3(0, legH * 0.85f + torsoH / 2, -0.07f * h),
                     new Vector3(shoulders * 1.15f, torsoH / 2 + legH * 0.18f, 0.2f * h), s.propC);
                break;
        }

        var col = root.AddComponent<CapsuleCollider>();   // ONE collider: the line-of-sight body
        col.height = s.height; col.center = new Vector3(0, s.height / 2, 0); col.radius = 0.28f;
        return root;
    }

    static void Part(GameObject root, PrimitiveType type, Vector3 localPos, Vector3 scale, Color c)
    {
        var p = GameObject.CreatePrimitive(type);
        Object.Destroy(p.GetComponent<Collider>());  // visuals only; the root capsule does physics
        p.transform.SetParent(root.transform, false);
        p.transform.localPosition = localPos;
        p.transform.localScale = scale;
        p.GetComponent<Renderer>().material.color = c;
    }
}
