// The night's SPINE — the authored pressure the scenario shelters from, enacted as timed,
// OBSERVABLE world events (never narration): a rider nails a crown warrant to the door mid-night,
// the ferry bell tolls as the water rises, and at dawn the horn — and the men it carries — arrive.
// The engine is never told what any of it MEANS: each character appraises what it witnesses
// (react recipe over /observe), so Corvin's dread is realized, not scripted.
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

public class StoryDirector : MonoBehaviour
{
    public static StoryDirector I;
    public bool WarrantUp { get; private set; }
    public Vector3 WarrantPos { get; private set; }

    public const string WarrantText =
        "BY ORDER OF THE CROWN — WANTED: the river-smuggler called THE HERON. Lean build, gray "
        + "eyes, a boatman's hands; known to run the north crossings. Forty crowns, dead or living. "
        + "The Crown's men ride at dawn.";

    GameObject warrantObj;
    AudioSource fx;

    void Awake() { I = this; }

    void Start()
    {
        fx = gameObject.AddComponent<AudioSource>();
        StartCoroutine(Night());
    }

    IEnumerator Night()
    {
        yield return Until(1.5f);   // the room settles first (hour 1.5 ≈ 3 real minutes)
        yield return NailUpWarrant();
        yield return Until(4f);
        fx.PlayOneShot(Bell(), 0.7f);
        yield return ReportToAll("the ferry bell tolls once through the storm — the water is still rising", 0.15f);
        yield return Until(8f);
        fx.PlayOneShot(Horn(), 0.9f);
        yield return ReportToAll("a horn sounds through the rain — the dawn ferry is coming in, "
                                 + "and with it voices: men in crown colors on the far landing", 0.5f);
        DialogueUI.I.Feed("—", "Dawn. The storm thins. The crossing will open soon.");
    }

    IEnumerator Until(float hour)
    {
        while (WorldClock.Hours < hour) yield return new WaitForSeconds(2f);
    }

    IEnumerator NailUpWarrant()
    {
        fx.PlayOneShot(Hammering(), 0.85f);  // three hard knocks from the door — everyone HEARS it
        yield return new WaitForSeconds(2.2f);
        WarrantPos = InnBuilder.WarrantAnchor != null ? InnBuilder.WarrantAnchor.position
                     : Regions.Anchor("the door") + new Vector3(0, 1.5f, -0.7f);
        warrantObj = GameObject.CreatePrimitive(PrimitiveType.Cube);
        warrantObj.name = "the crown warrant";
        warrantObj.transform.position = WarrantPos;
        warrantObj.transform.localScale = new Vector3(0.45f, 0.62f, 0.025f);
        warrantObj.GetComponent<Renderer>().material.color = new Color(0.9f, 0.85f, 0.7f);
        WarrantUp = true;
        DialogueUI.I.Feed("—", "Hammering at the door. When it stops, a paper is nailed there, ink running in the wet.");
        // Hearing needs no line of sight: every soul in the room heard the hammering.
        yield return ReportToAll("someone outside just hammered a paper to the inn door and rode off — "
                                 + "a crown notice, by the look of the seal", 0.4f);
    }

    /// A heard event: every NPC appraises it from its own life (no LoS gate — sound carries).
    public IEnumerator ReportToAll(string eventText, float magnitude)
    {
        if (MindClient.I == null || MindClient.I.SessionId == null) yield break;
        var items = NpcAgent.All.Select(a => new ObservedItem { slug = a.slug, observed = eventText }).ToArray();
        if (items.Length == 0) yield break;
        ObserveRes res = null;
        yield return MindClient.I.Observe(new ObserveReq
        { clock = WorldClock.Hours, magnitude = magnitude, items = items }, r => res = r);
        if (res == null) yield break;
        foreach (var r in res.results)
        {
            var npc = NpcAgent.All.FirstOrDefault(a => a.slug == r.slug);
            if (npc == null) continue;
            if (r.react == "speak") StartCoroutine(npc.SpeakBeat(eventText));
            else if (r.react == "act") StartCoroutine(npc.TakeBeat(eventText));
        }
    }

    public void OnThunder(float closeness)
    {
        if (closeness > 0.85f)  // only an overhead CRACK is an event; the rest is weather
            StartCoroutine(ReportToAll("a thunderclap cracks directly overhead — the whole inn shudders", 0.15f));
    }

    // ---- the warrant as a thing hands can reach ------------------------------------------------
    public void PlayerReads()
    {
        DialogueUI.I.Feed("The warrant", WarrantText);
        StartCoroutine(PlayerController.I.ReportAct("reads the crown warrant nailed to the door", 0.25f));
    }

    public void PlayerTears()
    {
        if (!WarrantUp) return;
        WarrantUp = false;
        Destroy(warrantObj);
        DialogueUI.I.Feed("—", "You tear the warrant down. The wet paper comes apart in your hands.");
        StartCoroutine(PlayerController.I.ReportAct("tears the crown warrant off the door and crumples it", 0.5f));
    }

    /// An NPC walked to the door and read it — the text enters THEIR memory at THEIR appraisal.
    public IEnumerator NpcReadsWarrant(NpcAgent npc)
    {
        if (!WarrantUp) yield break;
        ObserveRes res = null;
        yield return MindClient.I.Observe(new ObserveReq
        {
            clock = WorldClock.Hours,
            magnitude = 0.5f,
            items = new[] { new ObservedItem { slug = npc.slug,
                observed = $"you read the notice nailed to the door. {WarrantText}" } },
        }, r => res = r);
        if (res != null && res.results.Length > 0 && res.results[0].react == "speak")
            yield return npc.SpeakBeat("what the crown warrant on the door says");
    }

    // ---- tiny procedural one-shots (no assets, like the storm) ----------------------------------
    static AudioClip Hammering()
    {
        int sr = AudioSettings.outputSampleRate;
        var d = new float[sr * 2];
        for (int k = 0; k < 3; k++)
        {
            int start = (int)(k * 0.55f * sr);
            for (int i = 0; i < sr / 5; i++)
            {
                float t = i / (float)sr;
                d[start + i] += Mathf.Sin(2 * Mathf.PI * 70 * t) * Mathf.Exp(-t * 28f) * 0.9f;
            }
        }
        var c = AudioClip.Create("hammering", d.Length, 1, sr, false); c.SetData(d, 0); return c;
    }

    static AudioClip Bell()
    {
        int sr = AudioSettings.outputSampleRate;
        var d = new float[sr * 3];
        for (int i = 0; i < d.Length; i++)
        {
            float t = i / (float)sr;
            d[i] = (Mathf.Sin(2 * Mathf.PI * 440 * t) * 0.5f + Mathf.Sin(2 * Mathf.PI * 660 * t) * 0.3f)
                   * Mathf.Exp(-t * 1.6f) * 0.6f;
        }
        var c = AudioClip.Create("bell", d.Length, 1, sr, false); c.SetData(d, 0); return c;
    }

    static AudioClip Horn()
    {
        int sr = AudioSettings.outputSampleRate;
        var d = new float[sr * 3];
        for (int i = 0; i < d.Length; i++)
        {
            float t = i / (float)sr;
            float env = Mathf.Clamp01(t * 4f) * Mathf.Exp(-Mathf.Max(0, t - 1.8f) * 3f);
            d[i] = (Mathf.Sin(2 * Mathf.PI * 130 * t) + 0.5f * Mathf.Sin(2 * Mathf.PI * 195 * t)) * env * 0.5f;
        }
        var c = AudioClip.Create("horn", d.Length, 1, sr, false); c.SetData(d, 0); return c;
    }
}
