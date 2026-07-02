// The Ferry menu — the editor-side workflow: build the world INTO the open scene so it can be
// inspected and hand-adjusted before Play (Bootstrap detects it and keeps your edits), clear it,
// rebake the animator after mapping changes, and run the assembly smoke on demand.
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class QMenu
{
    [MenuItem("Ferry/Build World Into Scene")]
    public static void BuildWorld()
    {
        ClearWorld();
        InnBuilder.Build();
        ExteriorBuilder.Build();
        var marker = new GameObject("WorldMarker").AddComponent<WorldMarker>();
        marker.Capture();
        EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
        Debug.Log("Ferry: world built into the scene — inspect and adjust freely; Play will keep " +
                  "your edits. (Ferry > Clear Built World to go back to pure runtime building.)");
    }

    [MenuItem("Ferry/Clear Built World")]
    public static void ClearWorld()
    {
        foreach (var name in new[] { "Inn", "Exterior", "WorldMarker" })
        {
            var go = GameObject.Find(name);
            if (go != null) Object.DestroyImmediate(go);
        }
        // sweep any measuring probes a previous edit-mode build left below the world
        foreach (var t in Object.FindObjectsByType<Transform>(FindObjectsSortMode.None))
            if (t != null && t.parent == null && t.position.y < -100f && t.name.Contains("(Clone)"))
                Object.DestroyImmediate(t.gameObject);
        EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
    }

    [MenuItem("Ferry/Reimport Art (axis fix)")]
    public static void ReimportArt()
    {
        AssetDatabase.ImportAsset("Assets/Resources/Q",
            ImportAssetOptions.ImportRecursive | ImportAssetOptions.ForceUpdate);
        Debug.Log("Ferry: art reimported with baked axis conversion — rebuild the world or press Play.");
    }

    [MenuItem("Ferry/Rebake Animator")]
    public static void Rebake() => QBake.Bake();

    [MenuItem("Ferry/Run Assembly Smoke")]
    public static void Smoke() => QSmoke.Run();
}
