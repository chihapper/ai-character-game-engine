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

    void Start()
    {
        sr = AudioSettings.outputSampleRate;
        rain = gameObject.AddComponent<AudioSource>();
        rain.clip = MakeRain(8f);
        rain.loop = true;
        rain.volume = 0.32f;
        rain.Play();
        thunder = gameObject.AddComponent<AudioSource>();
        StartCoroutine(Storm());
    }

    IEnumerator Storm()
    {
        yield return new WaitForSeconds(4f);  // let the room settle, then the sky opens
        while (true)
        {
            float closeness = (float)rng.NextDouble();               // 1 = right overhead
            StartCoroutine(LightningFlash(closeness));
            yield return new WaitForSeconds(Mathf.Lerp(2.4f, 0.2f, closeness));
            thunder.PlayOneShot(MakeThunder(closeness), Mathf.Lerp(0.35f, 0.95f, closeness));
            if (StoryDirector.I != null) StoryDirector.I.OnThunder(closeness);  // an overhead CRACK is a world event
            yield return new WaitForSeconds(Random.Range(12f, 40f));
        }
    }

    IEnumerator LightningFlash(float closeness)
    {
        var sun = Bootstrap.Sun;
        if (sun == null) yield break;
        float baseI = sun.intensity;
        Color baseAmb = RenderSettings.ambientLight;
        int flickers = rng.Next(1, 3);
        for (int i = 0; i < flickers; i++)
        {
            sun.intensity = baseI + 2.4f * closeness;
            RenderSettings.ambientLight = baseAmb + Color.white * (0.45f * closeness);
            yield return new WaitForSeconds(0.05f);
            sun.intensity = baseI;
            RenderSettings.ambientLight = baseAmb;
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
