// Voice, both directions. OUT: each character's lines arrive as raw PCM in their OWN ElevenLabs
// voice and play as 3D audio at their body — Della's voice comes from behind the bar. IN: hold
// [V] to speak; the mic clip goes to AssemblyAI (batch) and your words become your line to
// whoever you're facing. [B] toggles voices off (TTS costs credits).
using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

public class VoiceClient : MonoBehaviour
{
    public static VoiceClient I;
    public static bool Enabled = true;      // server capability AND user toggle
    public static bool ServerHasVoice;

    void Awake() { I = this; }

    // ---- OUT: the character speaks ------------------------------------------------------------
    public void Speak(NpcAgent npc, string reply)
    {
        if (!Enabled || !ServerHasVoice || npc == null) return;
        var spoken = SpokenOnly(reply);
        if (string.IsNullOrWhiteSpace(spoken)) return;
        StartCoroutine(SpeakCo(npc, spoken));
    }

    IEnumerator SpeakCo(NpcAgent npc, string text)
    {
        var url = $"{MindClient.I.baseUrl}/{MindClient.I.SessionId}/{npc.slug}/speak";
        using var req = new UnityWebRequest(url, "POST");
        req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(
            JsonUtility.ToJson(new SpeakReq { text = text })));
        req.downloadHandler = new DownloadHandlerBuffer();
        req.SetRequestHeader("Content-Type", "application/json");
        req.timeout = 45;
        yield return req.SendWebRequest();
        if (req.result != UnityWebRequest.Result.Success) yield break;   // silent: text already shown
        int rate = int.TryParse(req.GetResponseHeader("X-Sample-Rate"), out var r) ? r : 24000;
        var pcm = req.downloadHandler.data;
        if (pcm == null || pcm.Length < 2 || npc == null) yield break;
        var samples = new float[pcm.Length / 2];
        for (int i = 0; i < samples.Length; i++)
            samples[i] = BitConverter.ToInt16(pcm, i * 2) / 32768f;
        var clip = AudioClip.Create("line", samples.Length, 1, rate, false);
        clip.SetData(samples, 0);
        var src = npc.GetComponent<AudioSource>() ?? npc.gameObject.AddComponent<AudioSource>();
        src.spatialBlend = 1f;
        src.minDistance = 1.6f;
        src.maxDistance = 18f;
        src.Stop();
        src.clip = clip;
        src.Play();
    }

    [Serializable] class SpeakReq { public string text; }

    /// Only what's between quotes gets a voice — narration stays on the page.
    public static string SpokenOnly(string s)
    {
        var parts = (s ?? "").Split('"');
        if (parts.Length < 3) return s;
        var sb = new StringBuilder();
        for (int i = 1; i < parts.Length; i += 2)
        { if (sb.Length > 0) sb.Append(" ... "); sb.Append(parts[i]); }
        return sb.ToString();
    }

    // ---- IN: the player speaks -----------------------------------------------------------------
    AudioClip mic;
    public bool Recording { get; private set; }

    public void BeginTalk()
    {
        if (Recording || Microphone.devices.Length == 0) return;
        mic = Microphone.Start(null, false, 20, 16000);
        Recording = true;
    }

    public void EndTalk(NpcAgent target)
    {
        if (!Recording) return;
        Recording = false;
        int pos = Microphone.GetPosition(null);
        Microphone.End(null);
        if (mic == null || pos < 16000 / 4) return;   // sub-quarter-second: a misclick, not speech
        var samples = new float[pos];
        mic.GetData(samples, 0);
        StartCoroutine(SttCo(Wav(samples, 16000), target));
    }

    IEnumerator SttCo(byte[] wav, NpcAgent target)
    {
        DialogueUI.I.Feed("—", "…listening…");
        var url = $"{MindClient.I.baseUrl}/{MindClient.I.SessionId}/stt";
        using var req = new UnityWebRequest(url, "POST");
        req.uploadHandler = new UploadHandlerRaw(wav);
        req.downloadHandler = new DownloadHandlerBuffer();
        req.SetRequestHeader("Content-Type", "application/octet-stream");
        req.timeout = 60;
        yield return req.SendWebRequest();
        if (req.result != UnityWebRequest.Result.Success)
        { DialogueUI.I.Feed("—", "(couldn't hear you — the words were lost to the storm)"); yield break; }
        var text = JsonUtility.FromJson<SttRes>(req.downloadHandler.text)?.text ?? "";
        if (string.IsNullOrWhiteSpace(text))
        { DialogueUI.I.Feed("—", "(nothing came through)"); yield break; }
        if (target != null) DialogueUI.I.VoiceSay(target, text);
        else DialogueUI.I.Feed("You (aloud, to no one)", text);
    }

    [Serializable] class SttRes { public string text; }

    static byte[] Wav(float[] samples, int rate)
    {
        var pcm = new byte[samples.Length * 2];
        for (int i = 0; i < samples.Length; i++)
        {
            short v = (short)Mathf.Clamp(samples[i] * 32767f, short.MinValue, short.MaxValue);
            pcm[i * 2] = (byte)(v & 0xff);
            pcm[i * 2 + 1] = (byte)((v >> 8) & 0xff);
        }
        using var ms = new System.IO.MemoryStream();
        using var w = new System.IO.BinaryWriter(ms);
        w.Write(Encoding.ASCII.GetBytes("RIFF"));
        w.Write(36 + pcm.Length);
        w.Write(Encoding.ASCII.GetBytes("WAVEfmt "));
        w.Write(16); w.Write((short)1); w.Write((short)1);
        w.Write(rate); w.Write(rate * 2); w.Write((short)2); w.Write((short)16);
        w.Write(Encoding.ASCII.GetBytes("data"));
        w.Write(pcm.Length);
        w.Write(pcm);
        return ms.ToArray();
    }
}
