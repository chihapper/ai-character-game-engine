// Editor-side driver for the autonomous visual loop: -executeMethod QShots.RunCLI (windowed, NOT
// batchmode — it must render). Writes the flag, enters play mode, waits for AutoShot's done
// marker, exits Unity. The build agent launches this, then reads the screenshots itself.
using System.IO;
using UnityEditor;
using UnityEngine;

public static class QShots
{
    static double deadline;

    [MenuItem("Ferry/Capture Auto Shots")]
    public static void RunCLI()
    {
        // capture the CURRENT CODE's world: fresh empty scene so Bootstrap builds at runtime
        // (a saved baked scene would replay old geometry and hide every fix under test)
        UnityEditor.SceneManagement.EditorSceneManager.NewScene(
            UnityEditor.SceneManagement.NewSceneSetup.DefaultGameObjects,
            UnityEditor.SceneManagement.NewSceneMode.Single);
        var root = Path.Combine(Application.dataPath, "..");
        File.Delete(Path.Combine(root, "autoshot.done"));
        File.WriteAllText(Path.Combine(root, "autoshot.flag"), "go");
        deadline = EditorApplication.timeSinceStartup + 240;
        EditorApplication.update += Watch;
        EditorApplication.EnterPlaymode();
    }

    static void Watch()
    {
        var root = Path.Combine(Application.dataPath, "..");
        bool done = File.Exists(Path.Combine(root, "autoshot.done"));
        if (!done && EditorApplication.timeSinceStartup < deadline) return;
        EditorApplication.update -= Watch;
        File.Delete(Path.Combine(root, "autoshot.flag"));
        if (Application.isBatchMode || System.Environment.CommandLine.Contains("QShots.RunCLI"))
            EditorApplication.Exit(done ? 0 : 2);
        else
            EditorApplication.ExitPlaymode();
    }
}
