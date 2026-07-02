// Self-bootstrapping gray-box ferry inn: an EMPTY scene plus these scripts is the whole game.
// Everything (room, regions, bodies, session) is built at runtime — no prefabs, no scene
// authoring, no packages — so the entire client is version-controlled as code.
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

public static class Regions
{
    static readonly Dictionary<string, Vector3> anchors = new();
    public static IEnumerable<string> Names => anchors.Keys;
    public static void Add(string name, Vector3 pos) => anchors[name] = pos;
    public static Vector3 Anchor(string name) =>
        anchors.TryGetValue(name, out var p) ? p : Vector3.zero;
    public static string NameAt(Vector3 pos) =>
        anchors.Count == 0 ? "the taproom"
        : anchors.OrderBy(kv => (kv.Value - pos).sqrMagnitude)
                 .Select(kv => (kv.Value - pos).sqrMagnitude <= 6.25f ? kv.Key : "the middle of the taproom")
                 .First();
}

public static class WorldClock
{
    public const float SecondsPerGameHour = 120f;  // the GAME owns the clock; the engine only differences it
    public static float Hours => Time.time / SecondsPerGameHour;
}

public class Bootstrap : MonoBehaviour
{
    public static string PlayerHandle = "the stranger just in from the storm";
    public static Light Sun;  // StormAudio flickers it for lightning

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void SelfSpawn() => new GameObject("Bootstrap").AddComponent<Bootstrap>();

    IEnumerator Start()
    {
        // The template scene (URP or Built-In) ships its own camera/listener — retire them so the
        // player's first-person camera is the only eye and ear in the room.
        foreach (var cam in FindObjectsByType<Camera>(FindObjectsSortMode.None))
            cam.gameObject.SetActive(false);
        foreach (var al in FindObjectsByType<AudioListener>(FindObjectsSortMode.None))
            al.enabled = false;
        BuildInn();
        var mind = gameObject.AddComponent<MindClient>();
        gameObject.AddComponent<DialogueUI>();
        yield return mind.CreateSession(s =>
        {
            PlayerHandle = string.IsNullOrEmpty(s.player_handle) ? PlayerHandle : s.player_handle;
            SpawnBodies(s);
            DialogueUI.I.Feed("—", $"{s.title} · the storm closes in. Find the bar.");
        });
    }

    void BuildInn()
    {
        RenderSettings.ambientLight = new Color(0.35f, 0.33f, 0.30f);
        Sun = new GameObject("Sun").AddComponent<Light>();
        Sun.type = LightType.Directional;
        Sun.intensity = 0.7f;
        Sun.transform.rotation = Quaternion.Euler(55, -30, 0);
        gameObject.AddComponent<StormAudio>();     // the storm the whole scenario shelters from
        gameObject.AddComponent<StoryDirector>();  // the night's spine — warrant, bell, dawn horn

        Box("floor", new Vector3(0, -0.1f, 0), new Vector3(14, 0.2f, 10), new Color(0.32f, 0.25f, 0.19f));
        // walls (occlusion is what makes line-of-sight REAL)
        Box("wall.n", new Vector3(0, 1.5f, 5), new Vector3(14, 3, 0.3f), Color.gray);
        Box("wall.s", new Vector3(0, 1.5f, -5), new Vector3(14, 3, 0.3f), Color.gray);
        Box("wall.e", new Vector3(7, 1.5f, 0), new Vector3(0.3f, 3, 10), Color.gray);
        Box("wall.w", new Vector3(-7, 1.5f, 0), new Vector3(0.3f, 3, 10), Color.gray);
        // fixtures — the bar counter is chest-high, so crouching behind it genuinely hides a body
        Box("the bar (counter)", new Vector3(4.5f, 0.6f, 2.5f), new Vector3(4, 1.2f, 0.8f), new Color(0.45f, 0.3f, 0.15f));
        Box("the hearth (stone)", new Vector3(-5.8f, 0.8f, 3.6f), new Vector3(1.6f, 1.6f, 1.2f), new Color(0.85f, 0.45f, 0.2f));
        Box("a corner table", new Vector3(-4.5f, 0.4f, -3.5f), new Vector3(1.4f, 0.8f, 1.4f), new Color(0.4f, 0.32f, 0.22f));
        Box("the window (shuttered)", new Vector3(6.8f, 1.6f, -3f), new Vector3(0.2f, 1.2f, 1.6f), new Color(0.25f, 0.3f, 0.4f));

        Regions.Add("the door", new Vector3(-1.5f, 0, -4.5f));
        Regions.Add("the bar", new Vector3(4.5f, 0, 1f));
        Regions.Add("the hearth", new Vector3(-5f, 0, 2.8f));
        Regions.Add("a corner table", new Vector3(-4.5f, 0, -2.5f));
        Regions.Add("the window", new Vector3(5.8f, 0, -3f));
    }

    void SpawnBodies(SessionRes s)
    {
        var spawns = new Dictionary<string, (string region, string stance, Color color)>
        {
            { "della-fenwick", ("the bar", "working the bar, wiping glasses", new Color(0.95f, 0.75f, 0.35f)) },
            { "corvin-ashgrave-inworld", ("the hearth", "back to the wall, nursing a cup, eyes on the door", new Color(0.45f, 0.6f, 0.95f)) },
            { "edwin-hale", ("the window", "dripping, watching the storm through the shutters", new Color(0.8f, 0.55f, 0.9f)) },
            { "brielle-bri-castellano", ("a corner table", "cloak shed, sitting straight, taking in the room", new Color(0.9f, 0.45f, 0.5f)) },
        };
        foreach (var c in s.cast)
        {
            var cfg = spawns.TryGetValue(c.slug, out var v) ? v
                      : ("the middle of the taproom", "", Color.white);
            var body = Capsule(c.handle, Regions.Anchor(cfg.Item1) + new Vector3(0.6f, 1, 0), cfg.Item3);
            var agent = body.AddComponent<NpcAgent>();
            agent.slug = c.slug; agent.handle = c.handle; agent.stance = cfg.Item2;
        }
        var player = Capsule("Player", Regions.Anchor("the door") + Vector3.up, new Color(0.5f, 0.85f, 0.65f));
        Destroy(player.GetComponent<Collider>());  // CharacterController replaces it
        player.AddComponent<PlayerController>();
    }

    static GameObject Box(string name, Vector3 pos, Vector3 size, Color color)
    {
        var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
        go.name = name; go.transform.position = pos; go.transform.localScale = size;
        go.GetComponent<Renderer>().material.color = color;
        return go;
    }

    static GameObject Capsule(string name, Vector3 pos, Color color)
    {
        var go = GameObject.CreatePrimitive(PrimitiveType.Capsule);
        go.name = name; go.transform.position = pos;
        go.GetComponent<Renderer>().material.color = color;
        return go;
    }
}
