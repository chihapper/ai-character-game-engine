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

        // The INPUT AREA draws FIRST: IMGUI keys a control's edit state to its sequence position,
        // so any variable-count controls (the feed) drawn before the text field would shift its
        // identity every time a line arrived — wiping whatever the player was mid-typing.
        if (IsOpen)
        {
            if (Event.current.type == EventType.KeyDown && Event.current.keyCode == KeyCode.Escape)
            { target = null; return; }
            bool enter = Event.current.type == EventType.KeyDown
                         && (Event.current.keyCode == KeyCode.Return || Event.current.keyCode == KeyCode.KeypadEnter);
            float ih = line * 2.4f;
            GUI.Box(new Rect(8, Screen.height - ih - 6, Screen.width - 16, ih),
                    waiting ? $"{target.Reference} …" : $"speaking to {target.Reference}", box);
            GUI.SetNextControlName("say");
            input = GUI.TextField(new Rect(16, Screen.height - line - 14,
                                           Screen.width - 150 - label.fontSize * 3, line), input, field);
            if (GUI.GetNameOfFocusedControl() != "say")
                GUI.FocusControl("say");
            bool submit = GUI.Button(new Rect(Screen.width - 130 - label.fontSize * 2,
                                              Screen.height - line - 14, 110 + label.fontSize * 2, line),
                                     "Say", button) || enter;
            if (submit && !waiting && input.Trim().Length > 0)
                StartCoroutine(Say(input.Trim()));
        }

        GUI.Label(new Rect(14, 8, Screen.width - 28, line),
                  $"hour {WorldClock.Hours:0.0}   [WASD] move  [E] talk  [Esc] close talk", label);
        // live interaction prompt — targeting must never fail silently
        var t = PlayerController.I != null ? PlayerController.I.Talkable : null;
        bool warrant = PlayerController.I != null && PlayerController.I.NearWarrant;
        if (!IsOpen && (t != null || warrant))
        {
            var msg = warrant ? "[E]  read the warrant    [T]  tear it down" : $"[E]  talk to {t.Reference}";
            var w = label.CalcSize(new GUIContent(msg)).x + 24;
            GUI.Box(new Rect((Screen.width - w) / 2, Screen.height * 0.62f, w, line + 6), GUIContent.none);
            GUI.Label(new Rect((Screen.width - w) / 2 + 12, Screen.height * 0.62f + 3, w, line), msg, label);
        }

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
