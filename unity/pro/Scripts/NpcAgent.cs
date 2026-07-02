// One NPC's life in the world: an idle cadence of perceive -> choose -> enact (the engine picks
// ONLY from afforded options — grounding by construction, same seam as the grid), plus reaction
// beats when /observe says an observed act crossed the game's salience policy.
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

public class NpcAgent : MonoBehaviour
{
    public static readonly List<NpcAgent> All = new();

    public string slug;
    public string handle;
    public string knownName = "";   // set the moment an introduction is actually spoken
    public string stance = "";
    public float walkSpeed = 1.6f;

    public string Reference => string.IsNullOrEmpty(knownName) ? handle : knownName;
    public Transform LookTarget;   // head turns toward this (talking partner, watched thing)
    // cross-talk guards (#31 lite): a pair doesn't re-open for a while, and the ROOM doesn't
    // chatter constantly — the option only even appears off cooldown
    static readonly Dictionary<string, float> pairTalk = new();
    static float roomTalk = -999f;
    Animator anim;
    Transform headBone;
    public bool busy { get; private set; }

    public void Bubble(string text)
    {
        (GetComponent<SpeechBubble>() ?? gameObject.AddComponent<SpeechBubble>()).Say(text, 2.25f);
    }

    void Awake()
    {
        anim = GetComponent<Animator>();
        if (anim != null && anim.isHuman) headBone = anim.GetBoneTransform(HumanBodyBones.Head);
    }

    // Post-animator head aim: believable attention without IK setup. Runs after the Animator so
    // the pose survives; small clamp keeps necks anatomical.
    void LateUpdate()
    {
        if (headBone == null) return;
        var t = LookTarget != null ? LookTarget
                : (stance.StartsWith("watching") && PlayerController.I != null
                   && stance.Contains("stranger") ? PlayerController.I.transform : null);
        if (t == null) return;
        var aim = (t.position + Vector3.up * 1.5f) - headBone.position;
        if (aim.sqrMagnitude < 0.05f) return;
        var target = Quaternion.LookRotation(aim);
        var local = Quaternion.Angle(transform.rotation, target);
        if (local > 75f) return;  // don't owl the neck
        headBone.rotation = Quaternion.Slerp(headBone.rotation, target, 0.5f);
    }

    void OnEnable() { All.Add(this); StartCoroutine(Life()); }
    void OnDisable() { All.Remove(this); }

    IEnumerator Life()
    {
        yield return new WaitForSeconds(Random.Range(8f, 20f));
        while (true)
        {
            if (!busy && MindClient.I != null && MindClient.I.SessionId != null)
                yield return TakeBeat("");
            yield return new WaitForSeconds(Random.Range(25f, 45f));  // idle cadence; #36 designs this properly
        }
    }

    /// A grounded action beat. `justNow` carries a fresh observation when this is a REACTION.
    public IEnumerator TakeBeat(string justNow)
    {
        busy = true;
        var scene = PerceptComposer.Render(this);
        if (!string.IsNullOrEmpty(justNow)) scene += $"\nJust now: {justNow}";
        var here = Regions.NameAt(transform.position);
        var options = Regions.Names.Where(n => n != here).Select(n => $"cross to {n}")
            .Concat(VisibleRefs().Select(r => $"watch {r}"))
            .Concat(IdleHere(here))
            .Append("stay where you are, watchful").ToList();
        if (StoryDirector.I != null && StoryDirector.I.WarrantUp)
            options.Add("go read the paper nailed to the door");
        // someone close enough to speak to, and the room is off chatter-cooldown (#31 lite)
        if (Time.time - roomTalk > 50f)
            foreach (var o in All)
                if (o != this && !o.busy
                    && Vector3.Distance(o.transform.position, transform.position) < 6f
                    && Time.time - PairKey(o) > 180f
                    && PerceptComposer.CanSee(transform, o.transform))
                    options.Add($"say a word to {o.Reference}");
        ChooseRes choice = null;
        yield return MindClient.I.Choose(slug, new ChooseReq { situation = scene, options = options.ToArray() },
                                         c => choice = c);
        if (choice != null && !string.IsNullOrEmpty(choice.action))
        {
            yield return Enact(choice.action, choice.reason);
            // the mind must KNOW the body did it — else "why did you come over?" gets confabulation
            if (!choice.action.StartsWith("stay where"))
                yield return MindClient.I.Acted(slug, choice.action, choice.reason);
        }
        busy = false;
    }

    /// A spoken reaction beat — the observed moment crossed SPEAK_SALIENCE.
    public IEnumerator SpeakBeat(string observed, Transform toward = null)
    {
        busy = true;
        anim?.SetBool("Talk", true);
        LookTarget = toward != null ? toward
                     : (PlayerController.I != null ? PlayerController.I.transform : null);
        RespondRes res = null;
        yield return MindClient.I.Respond(slug, new RespondReq
        {
            @event = $"Right now, before your eyes: {observed}. React as feels true to you.",
            situation = PerceptComposer.For(this),
        }, r => res = r);
        if (res != null)
        {
            if (!string.IsNullOrEmpty(res.name_spoken)) knownName = res.name_spoken;
            DialogueUI.I.Feed(Reference, res.reply);
            Bubble(res.reply);
            VoiceClient.I?.Speak(this, res.reply);
        }
        anim?.SetBool("Talk", false);
        LookTarget = null;
        busy = false;
    }

    // What a body can DO in the place it's standing — small stance-setting idles per region,
    // so the room reads lived-in instead of everyone pacing or freezing.
    static IEnumerable<string> IdleHere(string region)
    {
        switch (region)
        {
            case "the bar": yield return "lean at the bar"; break;
            case "the hearth": yield return "warm your hands at the fire"; break;
            case "a corner table": yield return "sit at the corner table"; break;
            case "the window": yield return "watch the storm through the shutters"; break;
            case "the door": yield return "listen at the door"; break;
        }
    }

    IEnumerable<string> VisibleRefs()
    {
        if (PlayerController.I != null && PerceptComposer.CanSee(transform, PlayerController.I.transform))
            yield return Bootstrap.PlayerHandle;
        foreach (var o in All)
            if (o != this && PerceptComposer.CanSee(transform, o.transform))
                yield return o.Reference;
    }

    float PairKey(NpcAgent o)
    {
        var k = string.CompareOrdinal(slug, o.slug) < 0 ? slug + "|" + o.slug : o.slug + "|" + slug;
        return pairTalk.TryGetValue(k, out var t) ? t : -999f;
    }

    void MarkPair(NpcAgent o)
    {
        var k = string.CompareOrdinal(slug, o.slug) < 0 ? slug + "|" + o.slug : o.slug + "|" + slug;
        pairTalk[k] = Time.time;
        roomTalk = Time.time;
    }

    /// #31 lite — one line spoken to another PRESENT character, heard by the room. The mind
    /// server needs nothing new: the line is respond(event=...), the listener HEARS it through
    /// /observe (their own appraisal decides whether to answer), and any reply is a SpeakBeat —
    /// which never itself triggers observation, so chatter can't chain into a loop.
    IEnumerator CrossTalk(NpcAgent other)
    {
        MarkPair(other);
        LookTarget = other.transform;
        anim?.SetBool("Talk", true);
        RespondRes res = null;
        yield return MindClient.I.Respond(slug, new RespondReq
        {
            @event = $"Say ONE brief line aloud to {other.Reference} — whatever this exact moment "
                     + "makes you want to say to them. A sentence or two, in quotes.",
            situation = PerceptComposer.For(this),
        }, r => res = r);
        anim?.SetBool("Talk", false);
        if (res == null || string.IsNullOrEmpty(res.reply)) { LookTarget = null; yield break; }
        if (!string.IsNullOrEmpty(res.name_spoken)) knownName = res.name_spoken;
        DialogueUI.I.Feed(Reference, res.reply);
        Bubble(res.reply);
        VoiceClient.I?.Speak(this, res.reply);
        other.LookTarget = transform;
        // the listener HEARS it — their appraisal decides if it deserves an answer
        ObserveRes ores = null;
        yield return MindClient.I.Observe(new ObserveReq
        {
            clock = WorldClock.Hours,
            magnitude = 0.2f,
            items = new[] { new ObservedItem { slug = other.slug,
                observed = $"{Reference} says to you: {res.reply}" } },
        }, r => ores = r);
        LookTarget = null;
        if (ores != null && ores.results.Length > 0 && ores.results[0].react != "")
            yield return other.SpeakBeat($"{Reference} just spoke to you: {res.reply} — answer them briefly", transform);
        else
            other.LookTarget = null;
    }

    IEnumerator Enact(string action, string reason)
    {
        if (action.StartsWith("say a word to "))
        {
            var who = action.Substring("say a word to ".Length);
            var other = All.FirstOrDefault(a => a != this && a.Reference == who);
            if (other != null) yield return CrossTalk(other);
            yield break;
        }
        if (action == "go read the paper nailed to the door")
        {
            stance = "";
            yield return WalkTo(Regions.Anchor("the door"));
            stance = "reading the notice on the door";
            if (!string.IsNullOrEmpty(reason)) DialogueUI.I.FeedAct(Reference, action, reason);
            yield return StoryDirector.I.NpcReadsWarrant(this);  // the text enters THEIR memory at THEIR appraisal
            yield break;
        }
        if (action.StartsWith("lean at") || action.StartsWith("warm your") || action.StartsWith("sit at")
            || action.StartsWith("listen at") || action.StartsWith("watch the storm"))
        {
            stance = action.Replace("your hands", "hands").Replace("your ", "");
            if (action.StartsWith("sit at") && InnBuilder.Seats.Count > 0)
            {
                // a body sits ON something: walk to the nearest seat, settle onto it, face the table
                var seat = InnBuilder.Seats.OrderBy(sp => (sp.pos - transform.position).sqrMagnitude).First();
                yield return WalkTo(seat.pos);
                transform.position = seat.pos + Vector3.up * 0.05f;
                var face = seat.face - transform.position; face.y = 0;
                if (face.sqrMagnitude > 0.01f) transform.rotation = Quaternion.LookRotation(face);
            }
            SetPose(action.StartsWith("sit at") ? "Sit" : action.StartsWith("lean at") ? "Lean" : "Arms");
            if (!string.IsNullOrEmpty(reason)) DialogueUI.I.FeedAct(Reference, action, reason);
            yield break;
        }
        if (action.StartsWith("cross to "))
        {
            stance = "";
            yield return WalkTo(Regions.Anchor(action.Substring(9)));
        }
        else if (action.StartsWith("watch "))
        {
            var who = action.Substring(6);
            stance = $"watching {who}";
            SetPose("Arms");
            var t = who == Bootstrap.PlayerHandle ? PlayerController.I.transform
                    : All.FirstOrDefault(a => a.Reference == who)?.transform;
            if (t != null)
            {
                var dir = t.position - transform.position; dir.y = 0;
                if (dir.sqrMagnitude > 0.01f) transform.rotation = Quaternion.LookRotation(dir);
            }
        }
        if (!string.IsNullOrEmpty(reason)) DialogueUI.I.FeedAct(Reference, action, reason);
    }

    void SetPose(string flag)
    {
        if (anim == null) return;
        foreach (var b in new[] { "Sit", "Lean", "Arms" }) anim.SetBool(b, b == flag);
    }

    IEnumerator WalkTo(Vector3 target)
    {
        SetPose("");  // a body that walks away stops sitting/leaning
        transform.position = new Vector3(transform.position.x, 0, transform.position.z);
        anim?.SetFloat("Speed", 1f);
        // Path AROUND the furniture (a straight line walked through the bar): NavMesh corners,
        // straight-line fallback where no path exists.
        var corners = new List<Vector3> { target };
        var path = new UnityEngine.AI.NavMeshPath();
        if (UnityEngine.AI.NavMesh.CalculatePath(transform.position, target, UnityEngine.AI.NavMesh.AllAreas, path)
            && path.corners.Length > 1)
            corners = path.corners.Skip(1).Select(c => new Vector3(c.x, 0, c.z)).ToList();
        foreach (var corner in corners)
        {
            while (Vector3.Distance(transform.position, corner) > 0.45f)
            {
                var dir = (corner - transform.position); dir.y = 0;
                transform.position += dir.normalized * walkSpeed * Time.deltaTime;
                if (dir.sqrMagnitude > 0.01f)
                    transform.rotation = Quaternion.Slerp(transform.rotation,
                        Quaternion.LookRotation(dir), 6f * Time.deltaTime);
                yield return null;
            }
        }
        anim?.SetFloat("Speed", 0f);
    }
}
