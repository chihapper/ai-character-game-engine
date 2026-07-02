// The #38 adapter: derive an agent's FIRST-PERSON percept from the real scene — line of sight by
// raycast, gaze by facing angle, proximity by distance — composed into the same present-strings
// the grid arena produced, now earned from actual space instead of tiles. The mind server passes
// these through untouched; the engine never learns what a raycast is.
using System.Collections.Generic;
using UnityEngine;

public static class PerceptComposer
{
    const float EyeHeight = 1.5f;
    const float GazeCone = 25f;  // degrees: within this, "looking your way" is geometry, not narration

    public static string ProximityTier(float d) =>
        d <= 1.3f ? "right beside you" : d <= 2.6f ? "close by" : d <= 5f ? "a few steps off"
                                                                          : "across the room";

    // Occlusion is REAL here: a body behind the bar or a wall simply is not in the percept.
    public static bool CanSee(Transform from, Transform to)
    {
        var a = from.position + Vector3.up * EyeHeight;
        var b = to.position + Vector3.up * 1.1f;
        return !Physics.Linecast(a, b, out var hit) || hit.transform.root == to.root;
    }

    public static bool IsLookingAt(Transform who, Transform target) =>
        Vector3.Angle(who.forward, target.position - who.position) < GazeCone;

    /// One present-line for `other` as seen by `observer` — null if out of sight.
    public static string PresentLine(Transform observer, Transform other, string reference, string stance)
    {
        if (!CanSee(observer, other)) return null;
        var bits = new List<string> { reference };
        if (!string.IsNullOrEmpty(stance)) bits.Add($"— {stance}");
        var d = Vector3.Distance(observer.position, other.position);
        var where = $"({Regions.NameAt(other.position)}, {ProximityTier(d)}";
        if (IsLookingAt(other, observer)) where += ", looking your way";
        bits.Add(where + ")");
        return string.Join(" ", bits);
    }

    /// The full situation for an NPC: everyone it can SEE (player included), from its own vantage.
    public static SituationDTO For(NpcAgent self)
    {
        var present = new List<string>();
        var player = PlayerController.I;
        if (player != null)
        {
            var line = PresentLine(self.transform, player.transform, Bootstrap.PlayerHandle, "");
            if (line != null) present.Add(line);
        }
        foreach (var other in NpcAgent.All)
            if (other != self)
            {
                var line = PresentLine(self.transform, other.transform, other.Reference, other.stance);
                if (line != null) present.Add(line);
            }
        return new SituationDTO
        {
            location = Regions.NameAt(self.transform.position),
            present = present.ToArray(),
            clock = WorldClock.Hours,
            ambient = StormAudio.Describe(),  // the storm is perceived world state, not just sound
        };
    }

    /// The rendered scene text `choose` grounds on (same shape the grid's render_player_view had).
    public static string Render(NpcAgent self)
    {
        var s = For(self);
        var lines = new List<string> { $"You're at {s.location}." };
        foreach (var p in s.present) lines.Add("- " + p);
        if (!string.IsNullOrEmpty(s.ambient)) lines.Add("Around you: " + s.ambient);
        return string.Join("\n", lines);
    }
}
