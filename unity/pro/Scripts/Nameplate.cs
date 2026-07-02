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
        go.transform.localPosition = new Vector3(0, height, 0);
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
        tm.text = text();
        tm.transform.rotation = Quaternion.LookRotation(  // face the player's camera
            tm.transform.position - Camera.main.transform.position);
    }
}
