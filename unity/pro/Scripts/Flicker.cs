// Firelight is never steady: Perlin-noise flicker on a Light's intensity (hearth breathes,
// oil lamps waver). Cheap, per-light, no assets.
using UnityEngine;

public class Flicker : MonoBehaviour
{
    public float baseIntensity = 1.5f;
    public float amount = 0.35f;   // how far it wanders
    public float speed = 1.6f;     // how restlessly
    Light lt;
    float seed;

    void Awake() { lt = GetComponent<Light>(); seed = Random.value * 100f; }

    void Update()
    {
        if (lt == null) return;
        float n = Mathf.PerlinNoise(seed, Time.time * speed) * 2f - 1f;
        lt.intensity = Mathf.Max(0.05f, baseIntensity + n * amount);
    }
}
