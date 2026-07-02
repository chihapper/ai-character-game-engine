// Editor-side driver for the autonomous visual loop: -executeMethod QShots.RunCLI (windowed, NOT
// batchmode — it must render). Writes the flag, enters play mode, waits for AutoShot's done
// marker, exits Unity. The build agent launches this, then reads the screenshots itself.
//
// The watcher must survive the domain reload that entering play mode triggers (a plain
// `EditorApplication.update += Watch` is wiped by it — the first rig run hung forever on that):
// [InitializeOnLoadMethod] re-arms it whenever the flag file exists, and the deadline derives
// from the flag file's mtime instead of editor-session state.
using System.IO;
using UnityEditor;
using UnityEngine;

public static class QShots
{
    const double DeadlineSecs = 300;

    static string Root => Path.Combine(Application.dataPath, "..");
    static string Flag => Path.Combine(Root, "autoshot.flag");
    static string Done => Path.Combine(Root, "autoshot.done");

    [MenuItem("Ferry/Capture Auto Shots")]
    public static void RunCLI()
    {
        // a compile error means play mode would run STALE assemblies — the shots would pass
        // or fail on code that isn't the code under test. Refuse loudly instead.
        if (EditorUtility.scriptCompilationFailed)
        {
            Debug.LogError("QSHOTS ABORT: script compilation failed — captures would test stale assemblies");
            if (Application.isBatchMode || System.Environment.CommandLine.Contains("QShots.RunCLI"))
                EditorApplication.Exit(3);
            return;
        }
        // capture the CURRENT CODE's world: fresh empty scene so Bootstrap builds at runtime
        // (a saved baked scene would replay old geometry and hide every fix under test)
        UnityEditor.SceneManagement.EditorSceneManager.NewScene(
            UnityEditor.SceneManagement.NewSceneSetup.DefaultGameObjects,
            UnityEditor.SceneManagement.NewSceneMode.Single);
        File.Delete(Done);
        File.WriteAllText(Flag, "go");
        Arm();
        EditorApplication.EnterPlaymode();
    }

    [InitializeOnLoadMethod]
    static void Rearm()
    {
        if (File.Exists(Flag)) Arm();
    }

    static void Arm()
    {
        EditorApplication.update -= Watch;   // never doubled
        EditorApplication.update += Watch;
    }

    static void Watch()
    {
        bool done = File.Exists(Done);
        double age = File.Exists(Flag)
            ? (System.DateTime.Now - File.GetLastWriteTime(Flag)).TotalSeconds
            : DeadlineSecs;
        if (!done && age < DeadlineSecs) return;
        EditorApplication.update -= Watch;
        File.Delete(Flag);
        if (Application.isBatchMode || System.Environment.CommandLine.Contains("QShots.RunCLI"))
            EditorApplication.Exit(done ? 0 : 2);
        else
            EditorApplication.ExitPlaymode();
    }
}
