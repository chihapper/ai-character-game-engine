// Words visible in SPACE: a wrapped, fading line over the speaker's head (the feed remains the
// transcript; this is where the room's voices live). TextMesh, no packages.
using UnityEngine;

public class SpeechBubble : MonoBehaviour
{
    TextMesh tm;
    float until;

    public void Say(string text, float height)
    {
        if (tm == null)
        {
            var go = new GameObject("bubble");
            go.transform.SetParent(transform, false);
            go.transform.localPosition = new Vector3(0, height / Mathf.Max(0.01f, transform.lossyScale.y), 0);  // parent is height-normalized
            tm = go.AddComponent<TextMesh>();
            tm.characterSize = 0.02f;
            tm.fontSize = 64;
            tm.anchor = TextAnchor.LowerCenter;
            tm.alignment = TextAlignment.Center;
            tm.color = new Color(1f, 0.98f, 0.92f);
        }
        tm.text = Wrap(Strip(text), 34);
        until = Time.time + Mathf.Clamp(2.5f + text.Length * 0.045f, 4f, 12f);
    }

    static string Strip(string s)
    {
        // spoken lines carry narration around the quotes — the bubble shows only what's SAID
        var parts = s.Split('"');
        if (parts.Length >= 3)
        {
            var spoken = new System.Text.StringBuilder();
            for (int i = 1; i < parts.Length; i += 2)
            { if (spoken.Length > 0) spoken.Append("  "); spoken.Append(parts[i]); }
            if (spoken.Length > 0) return spoken.ToString();
        }
        return s;
    }

    static string Wrap(string s, int width)
    {
        if (s.Length > 220) s = s.Substring(0, 217) + "…";
        var words = s.Split(' ');
        var sb = new System.Text.StringBuilder();
        int line = 0;
        foreach (var w in words)
        {
            if (line + w.Length + 1 > width) { sb.Append('\n'); line = 0; }
            else if (sb.Length > 0) { sb.Append(' '); line++; }
            sb.Append(w); line += w.Length;
        }
        return sb.ToString();
    }

    void LateUpdate()
    {
        if (tm == null) return;
        if (Time.time > until) { tm.text = ""; return; }
        if (Camera.main != null)
            tm.transform.rotation = Quaternion.LookRotation(
                tm.transform.position - Camera.main.transform.position);
        float left = until - Time.time;
        var c = tm.color; c.a = Mathf.Clamp01(left / 1.2f); tm.color = c;
    }
}
