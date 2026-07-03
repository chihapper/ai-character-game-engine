// THE BRIDGE: a persistent command channel into a LIVE editor — the fix for the cold-restart
// iteration loop (3-4 min per change) that made visual fixes crawl. The editor stays OPEN;
// the build agent drops a JSON command into bridge_cmd.json and reads bridge_result.json a
// few seconds later. Same architecture the "natural language Unity control" asset-store tools
// sell, built here so it composes with QShots/QBake/the mind server instead of replacing them.
//
// Commands (write to <project>/bridge_cmd.json):
//   {"op":"ping"}                                  -> alive check
//   {"op":"play"} / {"op":"stop"}                  -> enter/exit play mode
//   {"op":"build"}                                 -> Clear + Build world into the open scene
//   {"op":"bake"}                                  -> QBake.Bake()
//   {"op":"shot","a":"3,1.6,-2","b":"0,1,0","s":"view"}  -> camera at a, look at b, capture s.png
//   {"op":"xray"}                                  -> scene xray text into the result
//   {"op":"find","a":"Stool"}                      -> names+positions of matching objects
//   {"op":"move","a":"Inn/Barrel(Clone)","b":"1,0,2"}    -> reposition an object live
//   {"op":"state"}                                 -> play mode, cast count, animator states
using System;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class QBridge
{
    static string Root => Path.Combine(Application.dataPath, "..");
    static string CmdPath => Path.Combine(Root, "bridge_cmd.json");
    static string ResPath => Path.Combine(Root, "bridge_result.json");
    static double lastPoll;

    static QBridge() { EditorApplication.update += Poll; }

    static void Poll()
    {
        if (EditorApplication.timeSinceStartup - lastPoll < 0.5) return;
        lastPoll = EditorApplication.timeSinceStartup;
        if (!File.Exists(CmdPath)) return;
        string raw;
        try { raw = File.ReadAllText(CmdPath); File.Delete(CmdPath); }
        catch { return; }   // writer mid-write; next poll gets it
        string result;
        try { result = Run(raw); }
        catch (Exception e) { result = "ERROR: " + e.Message; }
        File.WriteAllText(ResPath, result);
    }

    static string Get(string raw, string key)
    {
        var m = System.Text.RegularExpressions.Regex.Match(raw, $"\"{key}\"\\s*:\\s*\"([^\"]*)\"");
        return m.Success ? m.Groups[1].Value : null;
    }

    static Vector3 V3(string s)
    {
        var p = s.Split(',').Select(x => float.Parse(x.Trim())).ToArray();
        return new Vector3(p[0], p[1], p[2]);
    }

    static string Run(string raw)
    {
        var op = Get(raw, "op");
        switch (op)
        {
            case "ping": return "pong " + DateTime.Now.ToString("HH:mm:ss");
            case "play": EditorApplication.EnterPlaymode(); return "entering play";
            case "stop": EditorApplication.ExitPlaymode(); return "exiting play";
            case "bake": QBake.Bake(); return "baked";
            case "build":
                QMenu.ClearWorld(); InnBuilder.Build(); ExteriorBuilder.Build();
                return "world built (edit mode; enter play for cast)";
            case "shot":
            {
                var cam = Camera.main ?? UnityEngine.Object.FindFirstObjectByType<Camera>();
                if (cam == null) return "ERROR: no camera";
                cam.transform.position = V3(Get(raw, "a"));
                cam.transform.rotation = Quaternion.LookRotation(V3(Get(raw, "b")) - cam.transform.position);
                var name = Get(raw, "s") ?? "bridge";
                var dir = Path.Combine(Root, "Screenshots", "bridge");
                Directory.CreateDirectory(dir);
                ScreenCapture.CaptureScreenshot(Path.Combine(dir, name + ".png"));
                return $"capturing {name}.png (allow ~1s to flush)";
            }
            case "find":
            {
                var q = (Get(raw, "a") ?? "").ToLower();
                var hits = UnityEngine.Object.FindObjectsByType<Transform>(FindObjectsSortMode.None)
                    .Where(t => t.name.ToLower().Contains(q)).Take(40)
                    .Select(t => $"{Path(t)} @ {t.position:F2}");
                return string.Join("\n", hits);
            }
            case "move":
            {
                var target = GameObject.Find(Get(raw, "a"));
                if (target == null) return "ERROR: not found " + Get(raw, "a");
                target.transform.position = V3(Get(raw, "b"));
                return $"moved {target.name} to {target.transform.position:F2}";
            }
            case "state":
            {
                var sb = new StringBuilder();
                sb.AppendLine($"playing={EditorApplication.isPlaying} compiling={EditorApplication.isCompiling}");
                foreach (var n in UnityEngine.Object.FindObjectsByType<NpcAgent>(FindObjectsSortMode.None))
                {
                    var a = n.GetComponent<Animator>();
                    var clip = a != null && a.GetCurrentAnimatorClipInfo(0).Length > 0
                        ? a.GetCurrentAnimatorClipInfo(0)[0].clip.name : "?";
                    sb.AppendLine($"{n.slug} pos={n.transform.position:F2} clip={clip} stance='{n.stance}'");
                }
                return sb.ToString();
            }
            default: return "ERROR: unknown op " + op;
        }
    }

    static string Path(Transform t) =>
        t.parent == null ? t.name : Path(t.parent) + "/" + t.name;
}
