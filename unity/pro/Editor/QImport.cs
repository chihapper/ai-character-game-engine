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
        // Axis bake is for STATIC art only (walls/props): baking vertex data on SKINNED meshes
        // (bodies, anims, hair, outfits) desyncs bind poses from bones — the exploded-marionette
        // playtest. Static architecture can never lie flat again; skinned things keep their rig
        // conventions and the runtime preserves their prefab rotations instead.
        bool skinned = assetPath.Contains("/Anims") || assetPath.Contains("Base Characters")
                       || assetPath.Contains("Hairstyles") || assetPath.Contains("/Outfits/");
        mi.bakeAxisConversion = !skinned;
        bool anims = assetPath.Contains("/Anims");
        bool body = assetPath.Contains("Base Characters");
        if (assetPath.Contains("/Outfits/") || assetPath.Contains("Hairstyles"))
        {
            // skinned meshes for the UBC rig (outfits: full skeleton; hair: one head bone):
            // Generic keeps the skeleton; the runtime remaps their bones onto the wearer's.
            // Rig=None here strips the skinning and hair lands as a static mesh at the feet.
            mi.animationType = ModelImporterAnimationType.Generic;
            mi.importAnimation = false;
            mi.isReadable = false;
            return;
        }
        if (anims || body)
        {
            mi.animationType = ModelImporterAnimationType.Human;
            mi.importAnimation = anims;
            if (anims) mi.animationCompression = ModelImporterAnimationCompression.Optimal;
            if (body) { mi.isReadable = true; return; }  // the head-only bake reads the mesh
        }
        else
        {
            mi.animationType = ModelImporterAnimationType.None;
            mi.importAnimation = false;
        }
        mi.isReadable = false;
    }
}
