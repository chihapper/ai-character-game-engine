// Minimal IMGUI dialogue + event feed — zero scene setup, zero UI packages. Talking composes the
// NPC's situation from ITS vantage (it knows where you're standing because it can see you).
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class DialogueUI : MonoBehaviour
{
    public static DialogueUI I;
    public bool IsOpen => target != null;

    NpcAgent target;
    string input = "";
    bool waiting;
    readonly List<string> feed = new();

    void Awake() { I = this; }

    public void Open(NpcAgent npc) { target = npc; input = ""; }
    public void Feed(string who, string text) { feed.Add($"{who}: {text}"); Trim(); }
    public void FeedAct(string who, string action, string reason) { feed.Add($"* {who} — {action} · “{reason}”"); Trim(); }
    void Trim() { while (feed.Count > 8) feed.RemoveAt(0); }

    void OnGUI()
    {
        GUI.Label(new Rect(12, 8, 800, 24),
                  $"hour {WorldClock.Hours:0.0}   [WASD] move  [E] talk  [Esc] close talk");
        float y = Screen.height - 40;
        for (int i = feed.Count - 1; i >= 0; i--, y -= 22)
            GUI.Label(new Rect(12, y - (IsOpen ? 64 : 0), Screen.width - 24, 22), feed[i]);

        if (!IsOpen) return;
        if (Event.current.type == EventType.KeyDown && Event.current.keyCode == KeyCode.Escape)
        { target = null; return; }

        GUI.Box(new Rect(8, Screen.height - 72, Screen.width - 16, 64),
                waiting ? $"{target.Reference} …" : $"speaking to {target.Reference}");
        GUI.SetNextControlName("say");
        input = GUI.TextField(new Rect(16, Screen.height - 44, Screen.width - 140, 26), input);
        GUI.FocusControl("say");
        bool submit = GUI.Button(new Rect(Screen.width - 116, Screen.height - 44, 100, 26), "Say")
                      || (Event.current.type == EventType.KeyDown && Event.current.keyCode == KeyCode.Return);
        if (submit && !waiting && input.Trim().Length > 0)
            StartCoroutine(Say(input.Trim()));
    }

    IEnumerator Say(string line)
    {
        waiting = true; input = "";
        Feed("You", line);
        var npc = target;
        RespondRes res = null;
        yield return MindClient.I.Respond(npc.slug,
            new RespondReq { line = line, situation = PerceptComposer.For(npc) }, r => res = r);
        if (res != null)
        {
            if (!string.IsNullOrEmpty(res.name_spoken)) npc.knownName = res.name_spoken;
            Feed(npc.Reference, res.reply);
        }
        waiting = false;
    }
}
