// Procedural fire: additive flame billboards + drifting embers, no assets. One call per fire —
// the hearth gets a big one, candles get pinpricks. Pairs with the Flicker light at the same spot.
using UnityEngine;

public static class FlameFX
{
    static Material flameMat;

    static Texture2D soft;

    /// A radial-falloff sprite generated in code — particles render as glows, not hard squares.
    public static Texture2D Soft()
    {
        if (soft != null) return soft;
        const int S = 64;
        soft = new Texture2D(S, S, TextureFormat.RGBA32, false);
        for (int y = 0; y < S; y++)
            for (int x = 0; x < S; x++)
            {
                float r = Vector2.Distance(new Vector2(x, y), new Vector2(S / 2f, S / 2f)) / (S / 2f);
                float a = Mathf.Clamp01(1f - r);
                soft.SetPixel(x, y, new Color(1, 1, 1, a * a));
            }
        soft.Apply();
        return soft;
    }

    static Material Mat()
    {
        if (flameMat != null) return flameMat;
        flameMat = new Material(Shader.Find("Universal Render Pipeline/Particles/Unlit")) { name = "flame" };
        flameMat.SetColor("_BaseColor", Color.white);
        flameMat.SetFloat("_Surface", 1);
        flameMat.SetOverrideTag("RenderType", "Transparent");
        flameMat.renderQueue = 3002;
        flameMat.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
        flameMat.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
        flameMat.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.One);  // additive: fire glows
        flameMat.SetInt("_ZWrite", 0);
        flameMat.SetTexture("_BaseMap", Soft());
        return flameMat;
    }

    public static void Add(Vector3 pos, float scale)
    {
        var go = new GameObject("flame");
        go.transform.position = pos;
        var ps = go.AddComponent<ParticleSystem>();
        var main = ps.main;
        main.startLifetime = new ParticleSystem.MinMaxCurve(0.35f * scale + 0.2f, 0.7f * scale + 0.3f);
        main.startSpeed = new ParticleSystem.MinMaxCurve(0.25f * scale, 0.7f * scale);
        main.startSize = new ParticleSystem.MinMaxCurve(0.06f * scale, 0.22f * scale);
        main.startColor = new ParticleSystem.MinMaxGradient(
            new Color(1f, 0.75f, 0.25f, 0.85f), new Color(1f, 0.4f, 0.1f, 0.8f));
        main.maxParticles = 80;
        var em = ps.emission; em.rateOverTime = 18f + 22f * scale;
        var shape = ps.shape;
        shape.shapeType = ParticleSystemShapeType.Cone;
        shape.angle = 8f; shape.radius = 0.05f * scale + 0.01f;
        var col = ps.colorOverLifetime; col.enabled = true;
        var g = new Gradient();
        g.SetKeys(
            new[] { new GradientColorKey(new Color(1f, 0.85f, 0.4f), 0),
                    new GradientColorKey(new Color(1f, 0.35f, 0.08f), 0.6f),
                    new GradientColorKey(new Color(0.4f, 0.1f, 0.05f), 1f) },
            new[] { new GradientAlphaKey(0.9f, 0), new GradientAlphaKey(0.55f, 0.5f), new GradientAlphaKey(0f, 1f) });
        col.color = g;
        var size = ps.sizeOverLifetime; size.enabled = true;
        size.size = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.EaseInOut(0, 1f, 1, 0.25f));
        go.GetComponent<ParticleSystemRenderer>().material = Mat();

        if (scale > 0.8f)  // embers off the big fire only
        {
            var e = new GameObject("embers");
            e.transform.position = pos + Vector3.up * 0.1f;
            var eps = e.AddComponent<ParticleSystem>();
            var em2 = eps.main;
            em2.startLifetime = 2.2f;
            em2.startSpeed = new ParticleSystem.MinMaxCurve(0.4f, 1.0f);
            em2.startSize = 0.02f;
            em2.startColor = new Color(1f, 0.55f, 0.15f, 0.9f);
            em2.maxParticles = 40;
            var er = eps.emission; er.rateOverTime = 5f;
            var evel = eps.velocityOverLifetime; evel.enabled = true;
            // ALL THREE axes must share a curve mode — leaving z at its default spams
            // "Particle Velocity curves must all be in the same mode" every frame
            evel.x = new ParticleSystem.MinMaxCurve(-0.15f, 0.15f);
            evel.y = new ParticleSystem.MinMaxCurve(0.5f, 1.1f);
            evel.z = new ParticleSystem.MinMaxCurve(-0.15f, 0.15f);
            e.GetComponent<ParticleSystemRenderer>().material = Mat();
        }
    }
}
