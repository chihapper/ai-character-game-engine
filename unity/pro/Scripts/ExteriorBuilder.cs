// The world OUTSIDE the windows — what a body sheltering from a storm should be able to look
// out at: rain falling in sheets, the flooded crossing lying black and swollen to the north,
// the marsh forest as silhouettes in the fog, a drowned jetty. Night + storm + exponential fog
// means silhouette-grade geometry reads as a real place; the mood does the rendering.
using UnityEngine;

public static class ExteriorBuilder
{
    public static void Build()
    {
        var root = new GameObject("Exterior").transform;
        var lit = Shader.Find("Universal Render Pipeline/Lit");

        Material M(string name, Color c, float smooth, bool emit = false, Color? emitC = null)
        {
            var m = new Material(lit) { name = name };
            m.SetColor("_BaseColor", c);
            m.SetFloat("_Smoothness", smooth);
            if (emit) { m.EnableKeyword("_EMISSION"); m.SetColor("_EmissionColor", emitC ?? Color.black); }
            return m;
        }

        // sodden ground around the inn
        var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
        ground.name = "mud";
        ground.transform.SetParent(root, false);
        ground.transform.localScale = new Vector3(16, 1, 16);      // 160m
        ground.transform.position = new Vector3(0, -0.02f, 0);
        ground.GetComponent<Renderer>().material = M("mud", new Color(0.16f, 0.14f, 0.12f), 0.55f);

        // THE FLOODED CROSSING — black water risen over the north bank, faintly sky-lit
        var water = GameObject.CreatePrimitive(PrimitiveType.Plane);
        water.name = "the crossing";
        Object.Destroy(water.GetComponent<Collider>());
        water.transform.SetParent(root, false);
        water.transform.localScale = new Vector3(30, 1, 14);
        water.transform.position = new Vector3(0, 0.06f, 78);
        var wm = M("water", new Color(0.05f, 0.07f, 0.1f), 0.75f, true, new Color(0.02f, 0.03f, 0.05f));
        water.GetComponent<Renderer>().material = wm;
        water.AddComponent<WaterShimmer>();

        // a drowned jetty running out into it
        for (int i = 0; i < 6; i++)
        {
            var plank = GameObject.CreatePrimitive(PrimitiveType.Cube);
            plank.transform.SetParent(root, false);
            plank.transform.position = new Vector3(2.5f, 0.25f - i * 0.04f, 10f + i * 2.2f);
            plank.transform.localScale = new Vector3(1.6f, 0.12f, 2.0f);
            plank.GetComponent<Renderer>().material = M("jetty", new Color(0.13f, 0.11f, 0.09f), 0.35f);
            if (i % 2 == 0)
            {
                var post = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                post.transform.SetParent(root, false);
                post.transform.position = new Vector3(3.4f, 0.5f - i * 0.06f, 10f + i * 2.2f);
                post.transform.localScale = new Vector3(0.18f, 0.6f, 0.18f);
                post.GetComponent<Renderer>().material = M("post", new Color(0.1f, 0.09f, 0.08f), 0.3f);
            }
        }

        // marsh forest — silhouette trees ringing the inn (never north: the water owns that view)
        var trunkM = M("trunk", new Color(0.08f, 0.075f, 0.07f), 0.2f);
        var canopyM = M("canopy", new Color(0.055f, 0.075f, 0.06f), 0.1f);
        var rng = new System.Random(7);
        for (int i = 0; i < 60; i++)
        {
            float ang = (float)(rng.NextDouble() * Mathf.PI * 2);
            float dist = 22f + (float)rng.NextDouble() * 34f;
            var pos = new Vector3(Mathf.Sin(ang) * dist, 0, Mathf.Cos(ang) * dist);
            if (pos.z > 12f && Mathf.Abs(pos.x) < 40f) continue;   // keep the water view open
            float h = 4f + (float)rng.NextDouble() * 5f;
            var trunk = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            trunk.transform.SetParent(root, false);
            trunk.transform.position = pos + Vector3.up * h * 0.35f;
            trunk.transform.localScale = new Vector3(0.3f, h * 0.35f, 0.3f);
            trunk.GetComponent<Renderer>().material = trunkM;
            var canopy = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            Object.Destroy(canopy.GetComponent<Collider>());
            canopy.transform.SetParent(root, false);
            canopy.transform.position = pos + Vector3.up * (h * 0.75f);
            canopy.transform.localScale = new Vector3(1.8f + (float)rng.NextDouble() * 1.6f, h * 0.45f, 1.8f);
            canopy.GetComponent<Renderer>().material = canopyM;
        }
        // reeds at the waterline
        for (int i = 0; i < 40; i++)
        {
            var reed = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            Object.Destroy(reed.GetComponent<Collider>());
            reed.transform.SetParent(root, false);
            reed.transform.position = new Vector3(-30f + (float)rng.NextDouble() * 60f, 0.5f,
                                                  11f + (float)rng.NextDouble() * 4f);
            reed.transform.localScale = new Vector3(0.05f, 0.5f + (float)rng.NextDouble() * 0.4f, 0.05f);
            reed.transform.rotation = Quaternion.Euler((float)rng.NextDouble() * 8f, 0, (float)rng.NextDouble() * 10f - 5f);
            reed.GetComponent<Renderer>().material = canopyM;
        }

        Rain(root);
    }

    /// Rain as sheets of stretched particles over the whole exterior — visible through every
    /// window, audible from StormAudio, and both track the same storm arc.
    static void Rain(Transform root)
    {
        var go = new GameObject("rain");
        go.transform.SetParent(root, false);
        go.transform.position = new Vector3(0, 14, 8);
        var ps = go.AddComponent<ParticleSystem>();
        var main = ps.main;
        main.loop = true;
        main.startLifetime = 1.1f;
        main.startSpeed = 15f;
        main.startSize3D = true;
        main.startSizeX = 0.025f; main.startSizeY = 0.9f; main.startSizeZ = 0.025f;
        main.startColor = new Color(0.6f, 0.68f, 0.8f, 0.28f);
        main.maxParticles = 4500;
        main.simulationSpace = ParticleSystemSimulationSpace.World;
        var emission = ps.emission; emission.rateOverTime = 2600f;
        var shape = ps.shape;
        shape.shapeType = ParticleSystemShapeType.Box;
        shape.scale = new Vector3(70f, 0.5f, 70f);
        var vel = ps.velocityOverLifetime;
        vel.enabled = true;
        vel.x = new ParticleSystem.MinMaxCurve(-1.6f);   // wind-driven slant
        vel.y = new ParticleSystem.MinMaxCurve(-14f);
        vel.z = new ParticleSystem.MinMaxCurve(0f);      // same curve mode on all three axes
        // the emission box overlaps the inn — without collision the streaks fall THROUGH the
        // ceiling into the taproom; they die on the roof collider instead
        var col = ps.collision;
        col.enabled = true;
        col.type = ParticleSystemCollisionType.World;
        col.mode = ParticleSystemCollisionMode.Collision3D;
        col.lifetimeLoss = 1f;
        col.quality = ParticleSystemCollisionQuality.High;
        var r = go.GetComponent<ParticleSystemRenderer>();
        r.renderMode = ParticleSystemRenderMode.Stretch;
        r.lengthScale = 6f;
        var m = new Material(Shader.Find("Universal Render Pipeline/Particles/Unlit")) { name = "rainmat" };
        m.SetColor("_BaseColor", new Color(0.6f, 0.68f, 0.8f, 0.28f));
        m.SetFloat("_Surface", 1);  // transparent
        m.SetOverrideTag("RenderType", "Transparent");
        m.renderQueue = 3000;
        m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
        m.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
        m.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
        m.SetInt("_ZWrite", 0);
        m.SetTexture("_BaseMap", FlameFX.Soft());
        r.material = m;
        go.AddComponent<RainIntensity>();
    }
}

/// The rain tracks the storm's arc — sheets at the peak, a thin drizzle by dawn.
public class RainIntensity : MonoBehaviour
{
    ParticleSystem ps;
    void Awake() { ps = GetComponent<ParticleSystem>(); }
    void Update()
    {
        var e = ps.emission;
        e.rateOverTime = Mathf.Lerp(120f, 2600f, StormAudio.Intensity);
    }
}

/// Slow shimmer on the flood water — a scrolling normal illusion via smoothness pulse.
public class WaterShimmer : MonoBehaviour
{
    Material m;
    void Awake() { m = GetComponent<Renderer>().material; }
    void Update()
    {
        m.SetFloat("_Smoothness", 0.68f + Mathf.PerlinNoise(Time.time * 0.35f, 0.5f) * 0.08f);
    }
}
