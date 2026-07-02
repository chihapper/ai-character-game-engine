// VRM pilot plumbing: the sample .vrm is a VRM-0.x file; the VRM-1.0 importer ignores it
// unless migration is enabled on the asset. This flips that switch headlessly and reports
// what the import produced (humanoid? blendshapes? materials?) so the pilot is data, not hope.
using System.Linq;
using UnityEditor;
using UnityEngine;

public static class QVrmProbe
{
    const string Path = "Assets/Resources/VRM/traveler.vrm";

    [MenuItem("Ferry/VRM Probe")]
    public static void Run()
    {
        var importer = AssetImporter.GetAtPath(Path);
        if (importer == null) { Debug.Log("QVRM: no importer for " + Path); return; }
        var so = new SerializedObject(importer);
        var prop = so.FindProperty("MigrateToVrm1") ?? so.FindProperty("m_migrateToVrm1");
        if (prop != null && !prop.boolValue)
        {
            prop.boolValue = true;
            so.ApplyModifiedPropertiesWithoutUndo();
            importer.SaveAndReimport();
            Debug.Log("QVRM: migration enabled, reimported");
        }
        var go = AssetDatabase.LoadAssetAtPath<GameObject>(Path);
        if (go == null) { Debug.Log("QVRM: no GameObject asset produced"); return; }
        var anim = go.GetComponent<Animator>();
        var smrs = go.GetComponentsInChildren<SkinnedMeshRenderer>(true);
        Debug.Log($"QVRM: prefab OK. humanoid={(anim != null && anim.avatar != null && anim.avatar.isHuman)} " +
                  $"smrs={smrs.Length} blendshapes={smrs.Sum(s => s.sharedMesh != null ? s.sharedMesh.blendShapeCount : 0)} " +
                  $"mats=[{string.Join(",", smrs.SelectMany(s => s.sharedMaterials).Where(m => m != null).Select(m => m.shader.name).Distinct())}]");
    }
}
