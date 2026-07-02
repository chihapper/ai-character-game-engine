// Minimal IMGUI dialogue + event feed — zero scene setup, zero UI packages. Talking composes the
// NPC's situation from ITS vantage (it knows where you're standing because it can see you).
// Text is scaled off screen height (IMGUI's default font is unreadably small on modern displays).
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
    GUIStyle label, box, field, button;

    void Awake() { I = this; }

    public void Open(NpcAgent npc) { target = npc; input = ""; }
    public void Feed(string who, string text) { feed.Add($"{who}: {text}"); Trim(); }
    public void FeedAct(string who, string action, string reason) { feed.Add($"* {who} — {action} · “{reason}”"); Trim(); }
    void Trim() { while (feed.Count > 6) feed.RemoveAt(0); }

    void EnsureStyles()
    {
        if (label != null) return;
        int size = Mathf.Max(16, Screen.height / 42);
        label = new GUIStyle(GUI.skin.label) { fontSize = size, wordWrap = true };
        label.normal.textColor = Color.white;
        box = new GUIStyle(GUI.skin.box) { fontSize = size, alignment = TextAnchor.UpperLeft };
        field = new GUIStyle(GUI.skin.textField) { fontSize = size };
        button = new GUIStyle(GUI.skin.button) { fontSize = size };
    }

    void OnGUI()
    {
        EnsureStyles();
        int line = label.fontSize + 8;
        GUI.Label(new Rect(14, 8, Screen.width - 28, line),
                  $"hour {WorldClock.Hours:0.0}   [WASD] move  [E] talk  [Esc] close talk", label);

        // feed: newest at the bottom, drawn upward, with a dark backdrop so it reads over the floor
        float inputPad = IsOpen ? line * 2.6f : 0;
        float y = Screen.height - line - 10 - inputPad;
        for (int i = feed.Count - 1; i >= 0; i--)
        {
            var h = label.CalcHeight(new GUIContent(feed[i]), Screen.width - 40);
            y -= h;
            GUI.Box(new Rect(10, y - 2, Screen.width - 20, h + 4), GUIContent.none);
            GUI.Label(new Rect(20, y, Screen.width - 40, h), feed[i], label);
        }

        if (!IsOpen) return;
        if (Event.current.type == EventType.KeyDown && Event.current.keyCode == KeyCode.Escape)
        { target = null; return; }

        float ih = line * 2.4f;
        GUI.Box(new Rect(8, Screen.height - ih - 6, Screen.width - 16, ih),
                waiting ? $"{target.Reference} …" : $"speaking to {target.Reference}", box);
        GUI.SetNextControlName("say");
        input = GUI.TextField(new Rect(16, Screen.height - line - 14, Screen.width - 150 - label.fontSize * 3, line), input, field);
        GUI.FocusControl("say");
        bool submit = GUI.Button(new Rect(Screen.width - 130 - label.fontSize * 2, Screen.height - line - 14,
                                          110 + label.fontSize * 2, line), "Say", button)
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
