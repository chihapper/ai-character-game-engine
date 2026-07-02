// The storm outside the inn — synthesized entirely in code (no audio assets, keeping the
// everything-is-generated property): rain = looped low-passed noise with a slow swell; thunder =
// decaying brown-noise rumbles at random closeness, preceded by a lightning flash on the sun
// light with a distance-scaled light-before-sound delay.
using System.Collections;
using UnityEngine;

public class StormAudio : MonoBehaviour
{
    AudioSource rain, thunder;
    readonly System.Random rng = new();
    int sr;
    static float lastCrack = -999f;

    /// The storm's ARC over the night (0..1): already heavy at the door, peaks mid-night, thins
    /// toward dawn. This is WORLD STATE — the sound tracks it, and every percept carries it
    /// (the rain thinning IS the crown men getting closer; a mind that can hear that feels the
    /// deadline, not just the weather).
    public static float Intensity
    {
        get
        {
            float h = WorldClock.Hours;
            if (h < 4f) return Mathf.Lerp(0.65f, 1f, h / 4f);
            return Mathf.Lerp(1f, 0.12f, (h - 4f) / 4f);
        }
    }

    public static string Describe()
    {
        float i = Mathf.Clamp01(Intensity);
        string sky = i > 0.85f ? "the storm is at full pitch — rain hammering the roof, the channel impassable"
                   : i > 0.6f ? "hard steady rain on the roof and shutters; the crossing stays shut"
                   : i > 0.35f ? "the rain is easing off — the worst of the storm has passed"
                   : "the storm is nearly spent; the rain thin, the water calming — the crossing will open soon";
        if (Time.time - lastCrack < 12f) sky += "; thunder just rolled through";
        return sky;
    }

    void Start()
    {
        sr = AudioSettings.outputSampleRate;
        rain = gameObject.AddComponent<AudioSource>();
        rain.clip = MakeRain(8f);
        rain.loop = true;
        rain.volume = 0.085f;  // ambience under the voices, never over them
        // heard THROUGH a roof: muffle the highs and the rain stops competing with speech
        var lp = gameObject.AddComponent<AudioLowPassFilter>();
        lp.cutoffFrequency = 1100f;
        rain.Play();
        thunder = gameObject.AddComponent<AudioSource>();
        // the hearth CRACKLES, in 3D at the fire itself — warmth you can hear across the room
        var crackleGo = new GameObject("crackle");
        crackleGo.transform.position = Regions.Anchor("the hearth") + new Vector3(-0.7f, 0.3f, 0);
        var crackle = crackleGo.AddComponent<AudioSource>();
        crackle.clip = MakeCrackle(6f);
        crackle.loop = true;
        crackle.volume = 0.55f;
        crackle.spatialBlend = 1f;
        crackle.minDistance = 1.2f;
        crackle.maxDistance = 12f;
        crackle.Play();
        // wind: slow gusts under the rain, tracking the same arc
        wind = gameObject.AddComponent<AudioSource>();
        wind.clip = MakeWind(10f);
        wind.loop = true;
        wind.volume = 0.06f;
        wind.Play();
        StartCoroutine(Storm());
    }

    AudioSource wind;

    IEnumerator Storm()
    {
        yield return new WaitForSeconds(4f);  // let the room settle, then the sky opens
        while (true)
        {
            float i = Intensity;
            rain.volume = 0.10f + 0.26f * i;                          // the sound TRACKS the arc
            if (wind != null) wind.volume = 0.06f + 0.22f * i;
            float closeness = (float)rng.NextDouble() * Mathf.Clamp01(i + 0.25f);
            StartCoroutine(LightningFlash(closeness));
            yield return new WaitForSeconds(Mathf.Lerp(2.4f, 0.2f, closeness));
            thunder.PlayOneShot(MakeThunder(closeness), Mathf.Lerp(0.18f, 0.5f, closeness));
            lastCrack = Time.time;
            if (StoryDirector.I != null) StoryDirector.I.OnThunder(closeness);  // an overhead CRACK is a world event
            yield return new WaitForSeconds(Random.Range(12f, 40f) / Mathf.Max(i, 0.25f));
        }
    }

    IEnumerator LightningFlash(float closeness)
    {
        var sun = Bootstrap.Sun;
        if (sun == null) yield break;
        float baseI = sun.intensity;
        Color baseAmb = RenderSettings.ambientLight;
        Color baseSun = sun.color;
        var paneBase = new Color(0.16f, 0.20f, 0.28f);
        var paneFlash = new Color(0.75f, 0.85f, 1f) * (1.5f + 6f * closeness);  // the windows go WHITE
        int flickers = rng.Next(1, 3);
        for (int i = 0; i < flickers; i++)
        {
            sun.intensity = baseI + 2.6f * closeness;
            sun.color = new Color(0.8f, 0.85f, 1f);
            RenderSettings.ambientLight = baseAmb + new Color(0.35f, 0.4f, 0.55f) * closeness;
            foreach (var m in Bootstrap.WindowPanes) m.SetColor("_EmissionColor", paneFlash);
            yield return new WaitForSeconds(0.05f);
            sun.intensity = baseI; sun.color = baseSun;
            RenderSettings.ambientLight = baseAmb;
            foreach (var m in Bootstrap.WindowPanes) m.SetColor("_EmissionColor", paneBase);
            yield return new WaitForSeconds(0.08f);
        }
    }

    AudioClip MakeRain(float seconds)
    {
        int n = (int)(sr * seconds);
        var d = new float[n];
        float hiss = 0, wash = 0;
        for (int i = 0; i < n; i++)
        {
            float white = (float)(rng.NextDouble() * 2 - 1);
            hiss += 0.12f * (white - hiss);   // droplet body
            wash += 0.02f * (white - wash);   // low wet wash
            float swell = 0.8f + 0.2f * Mathf.Sin(i * 2f * Mathf.PI * 0.11f / sr);
            d[i] = (hiss * 0.55f + wash * 0.9f) * swell;
        }
        int xf = sr / 4;  // crossfade the loop seam so the rain never clicks
        for (int i = 0; i < xf; i++)
        {
            float t = (float)i / xf;
            d[n - xf + i] = d[n - xf + i] * (1 - t) + d[i] * t;
        }
        Normalize(d, 0.85f);
        var clip = AudioClip.Create("rain", n, 1, sr, false);
        clip.SetData(d, 0);
        return clip;
    }

    AudioClip MakeCrackle(float seconds)
    {
        int n = (int)(sr * seconds);
        var d = new float[n];
        float hush = 0;
        for (int i = 0; i < n; i++)
        {
            float white = (float)(rng.NextDouble() * 2 - 1);
            hush += 0.03f * (white - hush);
            d[i] = hush * 0.5f;
        }
        for (int k = 0; k < seconds * 9; k++)   // the pops
        {
            int at = rng.Next(n - sr / 8);
            float amp = 0.25f + (float)rng.NextDouble() * 0.55f;
            int len = sr / 300 + rng.Next(sr / 200);
            for (int i = 0; i < len; i++)
                d[at + i] += (float)(rng.NextDouble() * 2 - 1) * amp * Mathf.Exp(-i * 9f / len);
        }
        int xf = sr / 5;
        for (int i = 0; i < xf; i++)
        { float t = (float)i / xf; d[n - xf + i] = d[n - xf + i] * (1 - t) + d[i] * t; }
        Normalize(d, 0.8f);
        var c = AudioClip.Create("crackle", n, 1, sr, false); c.SetData(d, 0); return c;
    }

    AudioClip MakeWind(float seconds)
    {
        int n = (int)(sr * seconds);
        var d = new float[n];
        float deep = 0;
        for (int i = 0; i < n; i++)
        {
            float white = (float)(rng.NextDouble() * 2 - 1);
            deep += 0.008f * (white - deep);   // very low rumble of moving air
            float gust = 0.45f + 0.55f * Mathf.PerlinNoise(i * 0.9f / sr, 0.3f);
            d[i] = deep * gust;
        }
        int xf = sr / 4;
        for (int i = 0; i < xf; i++)
        { float t = (float)i / xf; d[n - xf + i] = d[n - xf + i] * (1 - t) + d[i] * t; }
        Normalize(d, 0.85f);
        var c = AudioClip.Create("wind", n, 1, sr, false); c.SetData(d, 0); return c;
    }

    AudioClip MakeThunder(float closeness)
    {
        float dur = Mathf.Lerp(3f, 6f, closeness);
        int n = (int)(sr * dur);
        var d = new float[n];
        int strikes = rng.Next(2, 5);  // a crack rolls: overlapping rumbles at slight offsets
        for (int s = 0; s < strikes; s++)
        {
            int start = (int)(rng.NextDouble() * 0.35 * n);
            float decay = Mathf.Lerp(1.2f, 3.2f, (float)rng.NextDouble());
            float cutoff = Mathf.Lerp(0.015f, 0.07f, closeness);  // distant = only the lows survive
            float brown = 0, lp = 0;
            for (int i = start; i < n; i++)
            {
                float t = (i - start) / (float)sr;
                float env = Mathf.Exp(-t / decay);
                if (env < 0.001f) break;
                brown = Mathf.Clamp(brown + (float)(rng.NextDouble() * 2 - 1) * 0.12f, -1f, 1f);
                lp += cutoff * (brown - lp);
                d[i] += lp * env;
            }
        }
        Normalize(d, 0.95f);
        var clip = AudioClip.Create("thunder", n, 1, sr, false);
        clip.SetData(d, 0);
        return clip;
    }

    static void Normalize(float[] d, float peakTo)
    {
        float peak = 0;
        foreach (var v in d) peak = Mathf.Max(peak, Mathf.Abs(v));
        if (peak < 1e-5f) return;
        float k = peakTo / peak;
        for (int i = 0; i < d.Length; i++) d[i] *= k;
    }
}
