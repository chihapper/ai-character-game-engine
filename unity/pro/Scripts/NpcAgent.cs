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
    Animator anim;
    Transform headBone;
    bool busy;

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
    public IEnumerator SpeakBeat(string observed)
    {
        busy = true;
        anim?.SetBool("Talk", true);
        if (PlayerController.I != null) LookTarget = PlayerController.I.transform;
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

    IEnumerator Enact(string action, string reason)
    {
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

    IEnumerator WalkTo(Vector3 target)
    {
        anim?.SetFloat("Speed", walkSpeed);
        while (Vector3.Distance(transform.position, target) > 0.6f)
        {
            var dir = (target - transform.position); dir.y = 0;
            transform.position += dir.normalized * walkSpeed * Time.deltaTime;
            if (dir.sqrMagnitude > 0.01f)
                transform.rotation = Quaternion.Slerp(transform.rotation,
                    Quaternion.LookRotation(dir), 6f * Time.deltaTime);
            yield return null;
        }
        anim?.SetFloat("Speed", 0f);
    }
}
