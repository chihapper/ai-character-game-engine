// Import policy for everything under Assets/Resources/Q: character bodies and the animation
// libraries import as HUMANOID (one retargetable rig family — UAL clips drive UBC bodies);
// everything else (village modules, props, hair meshes) is static geometry. Materials import
// from FBX descriptions; the RUNTIME mapper (QMaterials.cs) replaces them with proper URP
// materials built from the packs' texture sheets, so no per-asset hand remapping exists anywhere.
using UnityEditor;

public class QImport : AssetPostprocessor
{
    void OnPreprocessModel()
    {
        if (!assetPath.Replace('\\', '/').Contains("/Resources/Q/")) return;
        var mi = (ModelImporter)assetImporter;
        bool anims = assetPath.Contains("/Anims");
        bool body = assetPath.Contains("Base Characters");
        if (anims || body)
        {
            mi.animationType = ModelImporterAnimationType.Human;
            mi.importAnimation = anims;
            if (anims) mi.animationCompression = ModelImporterAnimationCompression.Optimal;
        }
        else
        {
            mi.animationType = ModelImporterAnimationType.None;
            mi.importAnimation = false;
        }
        mi.isReadable = false;
    }
}
