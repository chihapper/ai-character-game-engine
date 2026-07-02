// A floating reference label — the acquaintance system made visible: it reads the appearance
// handle ("the ferrywoman") until the moment a name is actually spoken aloud, then flips to
// "Della". Bound to a live getter so the flip needs no wiring.
using System;
using UnityEngine;

public class Nameplate : MonoBehaviour
{
    public Func<string> text = () => "";
    public float height = 2.05f;
    TextMesh tm;

    void Start()
    {
        var go = new GameObject("nameplate");
        go.transform.SetParent(transform, false);
        go.transform.localPosition = new Vector3(0, height / Mathf.Max(0.01f, transform.lossyScale.y), 0);  // parent is height-normalized
        tm = go.AddComponent<TextMesh>();
        tm.characterSize = 0.022f;
        tm.fontSize = 64;
        tm.anchor = TextAnchor.LowerCenter;
        tm.alignment = TextAlignment.Center;
        tm.color = new Color(1f, 0.96f, 0.85f, 0.9f);
    }

    void LateUpdate()
    {
        if (tm == null || Camera.main == null) return;
        // fade out with distance — far plates overlap into an unreadable jumble and read
        // through walls; near ones are the ones that matter
        float d = Vector3.Distance(tm.transform.position, Camera.main.transform.position);
        float a = Mathf.InverseLerp(9f, 5.5f, d) * 0.9f;
        tm.color = new Color(1f, 0.96f, 0.85f, a);
        if (a <= 0.01f) { tm.text = ""; return; }
        tm.text = text();
        tm.transform.rotation = Quaternion.LookRotation(  // face the player's camera
            tm.transform.position - Camera.main.transform.position);
    }
}
