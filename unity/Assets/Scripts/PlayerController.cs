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

    void Awake()
    {
        I = this;
        cc = gameObject.AddComponent<CharacterController>();
        cc.height = 1.8f; cc.center = new Vector3(0, 0.9f, 0);
        cam = new GameObject("PlayerCam").AddComponent<Camera>();
        cam.transform.SetParent(transform, false);
        cam.transform.localPosition = new Vector3(0, 1.6f, 0);
        cam.gameObject.AddComponent<AudioListener>();
        lastRegion = Regions.NameAt(transform.position);
    }

    void Update()
    {
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

        var region = Regions.NameAt(transform.position);
        if (region != lastRegion)
        {
            lastRegion = region;
            StartCoroutine(ReportAct($"crosses to {region}", 0.1f));
        }

        if (Input.GetKeyDown(KeyCode.E))
        {
            var target = FacingNpc();
            if (target != null) DialogueUI.I.Open(target);
        }
    }

    NpcAgent FacingNpc() =>
        NpcAgent.All
            .Where(a => Vector3.Distance(a.transform.position, transform.position) < 3f
                        && PerceptComposer.IsLookingAt(transform, a.transform)
                        && PerceptComposer.CanSee(transform, a.transform))
            .OrderBy(a => Vector3.Distance(a.transform.position, transform.position))
            .FirstOrDefault();

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
