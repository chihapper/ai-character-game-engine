// One-shot audit: dump every AnimationClip inside the UAL library FBXs, so "do we need to buy
// animations?" is answered from data instead of memory.
using System.Linq;
using UnityEditor;
using UnityEngine;

public static class QAnimAudit
{
    [MenuItem("Ferry/Audit Animation Library")]
    public static void Run()
    {
        foreach (var path in new[] { "Assets/Resources/Q/Anims/Unity/UAL1_Standard.fbx",
                                     "Assets/Resources/Q/Anims2/Unity/UAL2_Standard.fbx" })
        {
            var clips = AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>()
                .Where(c => !c.name.StartsWith("__preview__"))
                .Select(c => $"{c.name} ({c.length:0.0}s)").OrderBy(n => n).ToList();
            Debug.Log($"ANIMAUDIT {path}: {clips.Count} clips\n" + string.Join("\n", clips));
        }
    }
}
