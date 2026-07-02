// The player's body: WASD + mouse look, E to talk to whoever you're facing. Crossing into a new
// region runs the react recipe over REAL witnesses — each NPC that can actually SEE you gets its
// own first-person observation (proximity from its own vantage); occlusion means unseen stays
// unremembered, for free.
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

public class PlayerController : MonoBehaviour
{
    public static PlayerController I;
    public float speed = 3.2f, lookSpeed = 2.2f;

    CharacterController cc;
    Camera cam;
    float pitch;
    string lastRegion = "";
    AudioSource stepSrc;
    AudioClip stepClip;
    float strideAcc;

    void Awake()
    {
        I = this;
        cc = gameObject.AddComponent<CharacterController>();
        cc.height = 1.8f; cc.center = new Vector3(0, 0.9f, 0);
        cam = new GameObject("PlayerCam").AddComponent<Camera>();
        cam.tag = "MainCamera";  // nameplates billboard toward Camera.main
        cam.transform.SetParent(transform, false);
        cam.transform.localPosition = new Vector3(0, 1.6f, 0);
        cam.gameObject.AddComponent<AudioListener>();
        lastRegion = Regions.NameAt(transform.position);
        stepSrc = gameObject.AddComponent<AudioSource>();
        stepClip = MakeStep();
    }

    void Update()
    {
        if (CurtainUI.GameEnded)
        { Cursor.lockState = CursorLockMode.None; Cursor.visible = true; return; }
        if (DialogueUI.I != null && DialogueUI.I.IsOpen)
        {
            Cursor.lockState = CursorLockMode.None; Cursor.visible = true;
            return;
        }
        Cursor.lockState = CursorLockMode.Locked; Cursor.visible = false;

        transform.Rotate(0, Input.GetAxis("Mouse X") * lookSpeed, 0);
        pitch = Mathf.Clamp(pitch - Input.GetAxis("Mouse Y") * lookSpeed, -70, 70);
        cam.transform.localEulerAngles = new Vector3(pitch, 0, 0);

        var move = transform.right * Input.GetAxis("Horizontal") + transform.forward * Input.GetAxis("Vertical");
        cc.SimpleMove(move.normalized * speed);

        // footsteps: one soft knock on the boards per ~0.75m of actual travel, pitch-jittered
        var flat = cc.velocity; flat.y = 0;
        strideAcc += flat.magnitude * Time.deltaTime;
        if (strideAcc > 0.75f && flat.magnitude > 0.5f)
        {
            strideAcc = 0;
            stepSrc.pitch = Random.Range(0.88f, 1.12f);
            stepSrc.PlayOneShot(stepClip, Random.Range(0.25f, 0.4f));
        }

        var region = Regions.NameAt(transform.position);
        if (region != lastRegion)
        {
            lastRegion = region;
            StartCoroutine(ReportAct($"crosses to {region}", 0.1f));
        }

        Talkable = FacingNpc();  // DialogueUI shows "[E] talk to …" whenever this is non-null
        NearWarrant = StoryDirector.I != null && StoryDirector.I.WarrantUp
                      && Vector3.Distance(transform.position, StoryDirector.I.WarrantPos) < 2.5f;
        if (NearWarrant)  // a paper nailed at eye height beats a conversation for the hands
        {
            if (Input.GetKeyDown(KeyCode.E)) StoryDirector.I.PlayerReads();
            if (Input.GetKeyDown(KeyCode.T)) StoryDirector.I.PlayerTears();
        }
        else if (Input.GetKeyDown(KeyCode.E) && Talkable != null)
            DialogueUI.I.Open(Talkable);
    }

    public NpcAgent Talkable { get; private set; }
    public bool NearWarrant { get; private set; }

    // Forgiving targeting: anyone visible within arm's-reach counts regardless of facing;
    // farther out (to 4m) requires roughly facing them. Strict cones read as "E does nothing".
    NpcAgent FacingNpc() =>
        NpcAgent.All
            .Where(a => PerceptComposer.CanSee(transform, a.transform))
            .Where(a =>
            {
                var d = Vector3.Distance(a.transform.position, transform.position);
                if (d < 2f) return true;
                return d < 4f && Vector3.Angle(transform.forward,
                    a.transform.position - transform.position) < 45f;
            })
            .OrderBy(a => Vector3.Distance(a.transform.position, transform.position))
            .FirstOrDefault();

    // A bootstep on old floorboards, synthesized (no assets, like the storm): a low knock plus a
    // brief wood-creak of filtered noise, both decaying fast.
    static AudioClip MakeStep()
    {
        int sr = AudioSettings.outputSampleRate;
        var rng = new System.Random();
        var d = new float[sr / 6];
        float lp = 0;
        for (int i = 0; i < d.Length; i++)
        {
            float t = i / (float)sr;
            float knock = Mathf.Sin(2 * Mathf.PI * 85 * t) * Mathf.Exp(-t * 40f);
            float white = (float)(rng.NextDouble() * 2 - 1);
            lp += 0.25f * (white - lp);
            float creak = lp * Mathf.Exp(-t * 25f) * 0.5f;
            d[i] = (knock + creak) * 0.8f;
        }
        var c = AudioClip.Create("step", d.Length, 1, sr, false);
        c.SetData(d, 0);
        return c;
    }

    /// The react recipe, client half: real witnesses only, each observation from ITS vantage.
    public IEnumerator ReportAct(string conseqThirdPerson, float magnitude)
    {
        if (MindClient.I == null || MindClient.I.SessionId == null) yield break;
        var items = new List<ObservedItem>();
        foreach (var npc in NpcAgent.All)
            if (PerceptComposer.CanSee(npc.transform, transform))
            {
                var d = Vector3.Distance(npc.transform.position, transform.position);
                items.Add(new ObservedItem
                {
                    slug = npc.slug,
                    observed = $"{Bootstrap.PlayerHandle} ({PerceptComposer.ProximityTier(d)}) {conseqThirdPerson}",
                });
            }
        if (items.Count == 0) yield break;
        ObserveRes res = null;
        yield return MindClient.I.Observe(new ObserveReq
        { clock = WorldClock.Hours, magnitude = magnitude, items = items.ToArray() }, r => res = r);
        if (res == null) yield break;
        foreach (var r in res.results)
        {
            var npc = NpcAgent.All.FirstOrDefault(a => a.slug == r.slug);
            var seen = items.First(i => i.slug == r.slug).observed;
            if (npc == null) continue;
            if (r.react == "speak") StartCoroutine(npc.SpeakBeat(seen));
            else if (r.react == "act") StartCoroutine(npc.TakeBeat(seen));
        }
    }
}
