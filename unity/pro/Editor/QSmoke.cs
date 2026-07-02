// Headless construction smoke (-executeMethod QSmoke.Run): assemble the ENTIRE world in the
// editor — inn, exterior, all four cast bodies — and report every missing prefab/texture and any
// exception. Compilation says the code parses; THIS says the world actually builds. The one kind
// of playtest that needs no player.
using System;
using System.Linq;
using UnityEditor;
using UnityEngine;

public static class QSmoke
{
    public static void Run()
    {
        int warned = 0;
        Application.logMessageReceived += (msg, stack, type) =>
        {
            if (type == LogType.Warning && (msg.Contains("missing prefab") || msg.Contains("unmapped material")))
            { warned++; Debug.Log("QSMOKE MISS: " + msg); }
        };
        try
        {
            InnBuilder.Build();
            Debug.Log($"QSMOKE inn built: panes={InnBuilder.WindowPanes.Count} seats={InnBuilder.Seats.Count} " +
                      $"warrantAnchor={(InnBuilder.WarrantAnchor != null)} wallH={InnBuilder.WallHeight:0.00}");
            ExteriorBuilder.Build();
            Debug.Log("QSMOKE exterior built");

            var looks = new (string name, CastLook look)[]
            {
                ("della", new CastLook { feminine = true, height = 0.98f, hair = "Hair_Buns" }),
                ("corvin", new CastLook { feminine = false, height = 1.04f, darkSkin = true, hair = "Hair_Buzzed", beard = true }),
                ("edwin", new CastLook { feminine = false, height = 0.99f, hair = "Hair_SimpleParted" }),
                ("bri", new CastLook { feminine = true, height = 0.93f, darkSkin = true, hair = "Hair_Long" }),
            };
            foreach (var (name, look) in looks)
            {
                var body = CastBuilder.Build(name, Vector3.zero, look);
                var anim = body.GetComponent<Animator>();
                var renderers = body.GetComponentsInChildren<Renderer>().Length;
                var hasCtrl = anim != null && anim.runtimeAnimatorController != null;
                var human = anim != null && anim.isHuman;
                Debug.Log($"QSMOKE cast {name}: renderers={renderers} humanoid={human} controller={hasCtrl}");
                if (!human || !hasCtrl) Debug.Log($"QSMOKE MISS: {name} human={human} ctrl={hasCtrl}");
            }

            // every Resources path the runtime loads by string — verify each resolves
            string[] paths =
            {
                "Q/NPCAnim",
                "Q/Props/Textures/T_Page_Noise",
                "Q/Characters/Base Characters/Textures/T_Superhero_Male_Ligh",
                "Q/Characters/Base Characters/Textures/T_Superhero_Male_Dark",
                "Q/Characters/Base Characters/Textures/T_Superhero_Female_Light_BaseColor",
                "Q/Characters/Base Characters/Textures/T_Superhero_Female_Dark_BaseColor",
            };
            foreach (var p in paths)
                if (Resources.Load(p) == null) { warned++; Debug.Log("QSMOKE MISS: Resources path " + p); }

            Debug.Log($"QSMOKE RESULT: {(warned == 0 ? "CLEAN" : warned + " MISSES")}");
        }
        catch (Exception e)
        {
            Debug.Log("QSMOKE EXCEPTION: " + e);
            EditorApplication.Exit(1);
        }
    }
}
