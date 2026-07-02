// The HTTP seam to the Python mind server (game/bridge/mind_api.py). Unity owns the WORLD;
// the server owns the MINDS. DTOs mirror the bridge exactly and stay JsonUtility-friendly
// (flat fields + arrays, no dicts). No package dependencies.
using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

// ---- DTOs ------------------------------------------------------------------------------------
[Serializable] public class CastEntry { public string slug; public string handle; public string here_because; }
[Serializable] public class SessionRes { public string session_id; public string title; public string player_handle; public float react_at; public float speak_at; public CastEntry[] cast; }
[Serializable] public class SituationDTO { public string location = ""; public string[] present = new string[0]; public float clock; public string performance = ""; }
[Serializable] public class RespondReq { public string line = ""; public string @event = ""; public SituationDTO situation = new SituationDTO(); }
[Serializable] public class RespondRes { public string reply; public string name_spoken; }
[Serializable] public class ChooseReq { public string situation = ""; public string[] options = new string[0]; }
[Serializable] public class ChooseRes { public string action; public string reason; }
[Serializable] public class ObservedItem { public string slug; public string observed; }
[Serializable] public class ObserveReq { public float clock; public float magnitude = 0.1f; public ObservedItem[] items = new ObservedItem[0]; }
[Serializable] public class ObserveResult { public string slug; public float salience; public string react; }
[Serializable] public class ObserveRes { public ObserveResult[] results; }
[Serializable] class SessionReq { public string scenario = "ferry_crossing.yaml"; public string reply_model = "claude-haiku-4-5"; }

public class MindClient : MonoBehaviour
{
    public static MindClient I;
    public string baseUrl = "http://127.0.0.1:8001/api/mind";
    public string SessionId { get; private set; }
    public SessionRes Session { get; private set; }

    void Awake() { I = this; }

    public IEnumerator CreateSession(Action<SessionRes> done)
    {
        yield return Post("/session", JsonUtility.ToJson(new SessionReq()), json =>
        {
            Session = JsonUtility.FromJson<SessionRes>(json);
            SessionId = Session.session_id;
            done?.Invoke(Session);
        });
    }

    public IEnumerator Respond(string slug, RespondReq req, Action<RespondRes> done) =>
        Post($"/{SessionId}/{slug}/respond", JsonUtility.ToJson(req),
             json => done?.Invoke(JsonUtility.FromJson<RespondRes>(json)));

    public IEnumerator Choose(string slug, ChooseReq req, Action<ChooseRes> done) =>
        Post($"/{SessionId}/{slug}/choose", JsonUtility.ToJson(req),
             json => done?.Invoke(JsonUtility.FromJson<ChooseRes>(json)));

    public IEnumerator Observe(ObserveReq req, Action<ObserveRes> done) =>
        Post($"/{SessionId}/observe", JsonUtility.ToJson(req),
             json => done?.Invoke(JsonUtility.FromJson<ObserveRes>(json)));

    public IEnumerator Finish() =>
        Post($"/{SessionId}/finish", "{\"outcome\":\"\"}", _ => { });

    IEnumerator Post(string path, string body, Action<string> onOk)
    {
        using var req = new UnityWebRequest(baseUrl + path, "POST");
        req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
        req.downloadHandler = new DownloadHandlerBuffer();
        req.SetRequestHeader("Content-Type", "application/json");
        req.timeout = 90;  // a respond spans an LLM call; v0 has no streaming (#37)
        yield return req.SendWebRequest();
        if (req.result != UnityWebRequest.Result.Success)
            Debug.LogWarning($"mind {path}: {req.responseCode} {req.downloadHandler.text}");
        else
            onOk?.Invoke(req.downloadHandler.text);
    }
}
