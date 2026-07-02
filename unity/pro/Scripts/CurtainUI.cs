// The curtain: a title card that fades up from black into the storm, and — when the dawn comes —
// an epilogue card that closes the night with what actually happened: whose names you earned,
// what became of the warrant, how the room ended. IMGUI, no packages; [R] restarts the night.
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.SceneManagement;

public class CurtainUI : MonoBehaviour
{
    public static CurtainUI I;
    public static bool GameEnded { get; private set; }

    float born;
    bool epilogue;
    string epilogueBody = "";
    GUIStyle title, sub, body;

    void Awake()
    {
        I = this; born = Time.time; GameEnded = false;
        // under the autoshot rig the title card would blanket every capture — skip it entirely
        // (self-destruct here is ordering-proof: AutoShot can't reliably find this component
        // because Bootstrap adds it later in its own coroutine)
        if (System.IO.File.Exists(System.IO.Path.Combine(Application.dataPath, "..", "autoshot.flag")))
            Destroy(this);
    }

    public void ShowEpilogue()
    {
        GameEnded = true;
        epilogue = true;
        var learned = NpcAgent.All.Where(a => !string.IsNullOrEmpty(a.knownName))
                                  .Select(a => a.knownName).ToList();
        var lines = new List<string>
        {
            $"You waited out the storm — {WorldClock.Hours:0.0} hours in the ferry inn.",
            learned.Count > 0 ? "Names the night gave you: " + string.Join(", ", learned) + "."
                              : "No one gave you their name. A room of strangers to the end.",
        };
        if (StoryDirector.I != null)
            lines.Add(StoryDirector.I.WarrantTorn
                ? "The crown's warrant ended the night as wet scraps in your fist."
                : StoryDirector.I.WarrantUp
                    ? "The crown's warrant still hangs on the door for the ferrymen to read."
                    : "The warrant never troubled the door.");
        lines.Add("");
        lines.Add("What they now think of you — they carry that with them.");
        epilogueBody = string.Join("\n", lines);
    }

    void EnsureStyles()
    {
        if (title != null) return;
        title = new GUIStyle(GUI.skin.label)
        { fontSize = Mathf.Max(34, Screen.height / 14), alignment = TextAnchor.MiddleCenter, fontStyle = FontStyle.Bold };
        title.normal.textColor = new Color(0.92f, 0.89f, 0.8f);
        sub = new GUIStyle(title) { fontSize = Mathf.Max(16, Screen.height / 38), fontStyle = FontStyle.Normal };
        sub.normal.textColor = new Color(0.75f, 0.75f, 0.78f);
        body = new GUIStyle(sub) { fontSize = Mathf.Max(15, Screen.height / 42) };
        body.normal.textColor = new Color(0.85f, 0.84f, 0.8f);
    }

    void OnGUI()
    {
        EnsureStyles();
        float t = Time.time - born;

        if (epilogue)
        {
            Black(0.92f);
            GUI.Label(new Rect(0, Screen.height * 0.16f, Screen.width, Screen.height * 0.2f), "DAWN", title);
            GUI.Label(new Rect(Screen.width * 0.15f, Screen.height * 0.38f, Screen.width * 0.7f, Screen.height * 0.4f),
                      epilogueBody, body);
            GUI.Label(new Rect(0, Screen.height * 0.85f, Screen.width, 40), "[R]  another night", sub);
            if (Event.current.type == EventType.KeyDown && Event.current.keyCode == KeyCode.R)
                SceneManager.LoadScene(SceneManager.GetActiveScene().buildIndex);
            return;
        }

        // opening: black -> title -> the room emerges as the card lifts
        if (t < 7.5f)
        {
            float a = t < 1f ? 1f : t < 5f ? 1f : Mathf.Clamp01(1f - (t - 5f) / 2.5f);
            Black(a);
            float ta = Mathf.Clamp01((t - 0.8f) / 1.4f) * Mathf.Clamp01(1f - (t - 4.6f) / 1.6f);
            var tc = title.normal.textColor; tc.a = ta; title.normal.textColor = tc;
            var sc = sub.normal.textColor; sc.a = ta; sub.normal.textColor = sc;
            GUI.Label(new Rect(0, Screen.height * 0.34f, Screen.width, Screen.height * 0.2f),
                      "THE FERRY'S LAST CROSSING", title);
            GUI.Label(new Rect(0, Screen.height * 0.54f, Screen.width, 60),
                      "a night among strangers", sub);
            tc.a = 1; title.normal.textColor = tc;
            sc.a = 1; sub.normal.textColor = sc;
        }
    }

    void Black(float a)
    {
        var c = GUI.color;
        GUI.color = new Color(0, 0, 0, a);
        GUI.DrawTexture(new Rect(0, 0, Screen.width, Screen.height), Texture2D.whiteTexture);
        GUI.color = c;
    }
}
