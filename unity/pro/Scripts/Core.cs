// Shared world primitives: named regions over real space, and the game clock (the game owns
// cadence and unit — the engine only ever differences the float).
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
                 .Select(kv => (kv.Value - pos).sqrMagnitude <= 7.5f ? kv.Key : "the middle of the taproom")
                 .First();
}

public static class WorldClock
{
    public const float SecondsPerGameHour = 120f;
    public static float Hours => Time.time / SecondsPerGameHour;
}
