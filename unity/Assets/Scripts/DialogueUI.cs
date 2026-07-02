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
    readonly List<string> feed = new();      // speech + story beats: bottom-left, above the composer
    readonly List<string> thoughts = new();  // NPC act beats + reasons: their OWN right-side column,
                                             // so an arriving thought never sits over what you're typing
    GUIStyle label, box, field, button, thought;

    void Awake() { I = this; }

    public void Open(NpcAgent npc) { target = npc; input = ""; }
    public void Feed(string who, string text) { feed.Add($"{who}: {text}"); Trim(feed, 6); }
    public void FeedAct(string who, string action, string reason)
    { thoughts.Add($"{who} — {action}\n“{reason}”"); Trim(thoughts, 5); }
    static void Trim(List<string> l, int keep) { while (l.Count > keep) l.RemoveAt(0); }

    void EnsureStyles()
    {
        if (label != null) return;
        int size = Mathf.Max(16, Screen.height / 42);
        label = new GUIStyle(GUI.skin.label) { fontSize = size, wordWrap = true };
        label.normal.textColor = Color.white;
        box = new GUIStyle(GUI.skin.box) { fontSize = size, alignment = TextAnchor.UpperLeft };
        field = new GUIStyle(GUI.skin.textField) { fontSize = size };
        button = new GUIStyle(GUI.skin.button) { fontSize = size };
        thought = new GUIStyle(GUI.skin.label)
        { fontSize = Mathf.RoundToInt(size * 0.85f), wordWrap = true, fontStyle = FontStyle.Italic };
        thought.normal.textColor = new Color(0.85f, 0.88f, 1f, 0.95f);
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

        // SPEECH feed: bottom-LEFT (60% width), newest at the bottom, drawn upward above the composer
        float feedW = Screen.width * 0.60f;
        float inputPad = IsOpen ? line * 2.6f : 0;
        float y = Screen.height - line - 10 - inputPad;
        for (int i = feed.Count - 1; i >= 0; i--)
        {
            var h = label.CalcHeight(new GUIContent(feed[i]), feedW - 30);
            y -= h;
            GUI.Box(new Rect(10, y - 2, feedW, h + 4), GUIContent.none);
            GUI.Label(new Rect(20, y, feedW - 30, h), feed[i], label);
        }

        // THOUGHT column: right side (28% width), top-down, italic + dim — the room's inner life
        // stays visible while you type without ever covering the composer or the speech feed
        float tw = Screen.width * 0.28f;
        float tx = Screen.width - tw - 12;
        float ty = line * 1.6f;
        foreach (var t2 in thoughts)
        {
            var h = thought.CalcHeight(new GUIContent(t2), tw - 20);
            GUI.Box(new Rect(tx, ty - 2, tw, h + 6), GUIContent.none);
            GUI.Label(new Rect(tx + 10, ty + 1, tw - 20, h), t2, thought);
            ty += h + 10;
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
