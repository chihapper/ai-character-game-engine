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
    bool busy;

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
            .Append("stay where you are, watchful").ToArray();
        ChooseRes choice = null;
        yield return MindClient.I.Choose(slug, new ChooseReq { situation = scene, options = options },
                                         c => choice = c);
        if (choice != null && !string.IsNullOrEmpty(choice.action))
            yield return Enact(choice.action, choice.reason);
        busy = false;
    }

    /// A spoken reaction beat — the observed moment crossed SPEAK_SALIENCE.
    public IEnumerator SpeakBeat(string observed)
    {
        busy = true;
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
        busy = false;
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
        if (action.StartsWith("cross to "))
        {
            stance = "";
            var target = Regions.Anchor(action.Substring(9));
            while (Vector3.Distance(transform.position, target) > 0.6f)
            {
                var dir = (target - transform.position); dir.y = 0;
                transform.position += dir.normalized * walkSpeed * Time.deltaTime;
                if (dir.sqrMagnitude > 0.01f)
                    transform.rotation = Quaternion.Slerp(transform.rotation,
                        Quaternion.LookRotation(dir), 6f * Time.deltaTime);
                yield return null;
            }
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
}
