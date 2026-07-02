// Runtime material factory for the Quaternius packs: FBX-imported materials are replaced with
// proper URP Lit materials built from the packs' texture sheets, mapped by the FBX material's
// NAME — so there is no per-asset hand remapping anywhere, and a new prop just works. Unknown
// names get a warm neutral and a console note (the iteration signal).
using System.Collections.Generic;
using UnityEngine;

public static class QMaterials
{
    static readonly Dictionary<string, Material> cache = new();
    static Shader lit;

    static Material Make(string key, string baseTex, string normalTex = null, string ormTex = null,
                         Color? tint = null, float smooth = 0.25f)
    {
        if (cache.TryGetValue(key, out var m)) return m;
        lit ??= Shader.Find("Universal Render Pipeline/Lit");
        m = new Material(lit) { name = "Q_" + key };
        var t = baseTex != null ? Resources.Load<Texture2D>(baseTex) : null;
        if (t != null) m.SetTexture("_BaseMap", t);
        m.SetColor("_BaseColor", tint ?? Color.white);
        var n = normalTex != null ? Resources.Load<Texture2D>(normalTex) : null;
        if (n != null) { m.EnableKeyword("_NORMALMAP"); m.SetTexture("_BumpMap", n); }
        m.SetFloat("_Smoothness", smooth);
        cache[key] = m;
        return m;
    }

    const string VT = "Q/Village/Textures/";
    const string PT = "Q/Props/Textures/";
    const string CT = "Q/Characters/Base Characters/Textures/";

    /// Map one FBX material name to a real URP material.
    public static Material Map(string fbxMatName)
    {
        var s = (fbxMatName ?? "").ToLower().Replace(" (instance)", "");
        // characters
        if (s.Contains("male") && !s.Contains("female")) return Make("body_m", CT + "T_Superhero_Male_Ligh", null, null, null, 0.15f);
        if (s.Contains("female")) return Make("body_f", CT + "T_Superhero_Female_Light_BaseColor", null, null, null, 0.15f);
        if (s.Contains("eye")) return Make("eye", CT + "T_Eye_Brown", null, null, null, 0.5f);
        if (s.Contains("hair") || s.Contains("beard") || s.Contains("brow"))
            return Make("hair", CT + "T_Hair_1_BaseColor", null, null, null, 0.3f);
        // village architecture
        if (s.Contains("plaster")) return Make("plaster", VT + "T_Plaster_BaseColor", VT + "T_Plaster_Normal", null, new Color(0.93f, 0.9f, 0.85f), 0.1f);
        if (s.Contains("brick")) return Make("brick", VT + "T_Brick_BaseColor", VT + "Normals Godot-Unity/T_Brick_Normal", null, null, 0.12f);
        if (s.Contains("uneven")) return Make("uneven", VT + "T_UnevenBrick_BaseColor", VT + "T_UnevenBrick_Normal", null, null, 0.1f);
        if (s.Contains("rock")) return Make("rock", VT + "T_RockTrim_BaseColor", VT + "Normals Godot-Unity/T_RockTrim_Normal", null, null, 0.1f);
        if (s.Contains("roof") || s.Contains("tile")) return Make("roof", VT + "T_RoundTiles_BaseColor", VT + "T_RoundTiles_Normal", null, new Color(0.6f, 0.45f, 0.4f), 0.1f);
        if (s.Contains("topwear")) return Make("topwear", CT + "T_TopWear", null, null, null, 0.12f);
        if (s.Contains("bottomwear")) return Make("bottomwear", CT + "T_BottomWear", null, null, null, 0.12f);
        if (s.Contains("wood") || s.Contains("plank") || s.Contains("beam") || s.Contains("frame"))
            return Make("wood", VT + "T_WoodTrim_BaseColor", VT + "T_WoodTrim_Normal", null, new Color(0.9f, 0.84f, 0.76f), 0.15f);
        if (s.Contains("glass") || s.Contains("window")) return Make("glass", null, null, null, new Color(0.45f, 0.52f, 0.62f), 0.85f);
        // props trim sheets
        if (s.Contains("cloth") || s.Contains("banner") || s.Contains("fabric")) return Make("t_cloth", PT + "T_Trim_Cloth_BaseColor", PT + "T_Trim_Cloth_Normal", null, null, 0.1f);
        if (s.Contains("metal") || s.Contains("iron")) return Make("t_metal", PT + "T_Trim_Metal_BaseColor", PT + "T_Trim_Metal_Normal", null, null, 0.55f);
        if (s.Contains("furniture")) return Make("t_furn", PT + "T_Trim_Furniture_BaseColor", PT + "T_Trim_Furniture_Normal", null, null, 0.2f);
        if (s.Contains("props") || s.Contains("prop")) return Make("t_props", PT + "T_Trim_Props_BaseColor", PT + "T_Trim_Props_Normal", null, null, 0.25f);
        if (s.Contains("page") || s.Contains("paper") || s.Contains("scroll")) return Make("paper", null, null, null, new Color(0.9f, 0.85f, 0.72f), 0.05f);
        Debug.Log($"QMaterials: unmapped material '{fbxMatName}' — warm neutral used");
        return Make("fallback_" + s, null, null, null, new Color(0.6f, 0.55f, 0.5f), 0.2f);
    }

    /// Replace every renderer's materials in `root` via the name map. Optional tint multiplies
    /// base color (used to differentiate cast outfits without new textures).
    public static void Apply(GameObject root, Color? tint = null)
    {
        foreach (var r in root.GetComponentsInChildren<Renderer>(true))
        {
            var mats = r.sharedMaterials;
            for (int i = 0; i < mats.Length; i++)
            {
                var mapped = Map(mats[i] ? mats[i].name : "");
                if (tint.HasValue)
                {
                    mapped = new Material(mapped);
                    mapped.SetColor("_BaseColor", mapped.GetColor("_BaseColor") * tint.Value);
                }
                mats[i] = mapped;
            }
            r.sharedMaterials = mats;
        }
    }
}
