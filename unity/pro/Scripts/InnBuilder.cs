// The ferry inn, built from Medieval Village MegaKit modules + Fantasy Props at runtime — same
// all-code philosophy as the gray box, but with real walls, windows, and furniture. Module size
// is MEASURED from the assets (never assumed), the layout tiles from it, and invisible box
// colliders carry physics (line of sight + player movement) so mesh import stays lean.
using System.Collections.Generic;
using UnityEngine;

public static class InnBuilder
{
    const string V = "Q/Village/FBX/";
    const string P = "Q/Props/Exports/FBX/";

    public static readonly List<Material> WindowPanes = new();
    public static Transform WarrantAnchor { get; private set; }
    public static float WallHeight { get; private set; } = 3f;

    static Transform root;

    static GameObject Spawn(string path, Vector3 pos, float yRot = 0, Vector3? scale = null)
    {
        var prefab = Resources.Load<GameObject>(path);
        if (prefab == null) { Debug.LogWarning($"InnBuilder: missing prefab {path}"); return null; }
        var go = Object.Instantiate(prefab, pos, Quaternion.Euler(0, yRot, 0), root);
        if (scale.HasValue) go.transform.localScale = scale.Value;
        QMaterials.Apply(go);
        return go;
    }

    static Vector3 Size(string path)
    {
        var prefab = Resources.Load<GameObject>(path);
        if (prefab == null) return Vector3.one * 2;
        var b = new Bounds(Vector3.zero, Vector3.zero);
        bool first = true;
        foreach (var r in prefab.GetComponentsInChildren<MeshRenderer>())
        { if (first) { b = r.bounds; first = false; } else b.Encapsulate(r.bounds); }
        return b.size;
    }

    static void BoxCollider(Vector3 center, Vector3 size)
    {
        var go = new GameObject("col");
        go.transform.SetParent(root, false);
        go.transform.position = center;
        var c = go.AddComponent<BoxCollider>();
        c.size = size;
    }

    public static void Build()
    {
        root = new GameObject("Inn").transform;
        var wall = Size(V + "Wall_Plaster_Straight");
        float U = Mathf.Max(1f, wall.x);          // module unit, measured
        WallHeight = Mathf.Max(2.2f, wall.y);
        int nx = Mathf.Max(3, Mathf.RoundToInt(12f / U));   // ~12m wide
        int nz = Mathf.Max(2, Mathf.RoundToInt(9f / U));    // ~9m deep
        float W = nx * U, D = nz * U;
        float x0 = -W / 2, z0 = -D / 2;

        // floor + ceiling from wood floor tiles
        var ftile = Size(V + "Floor_WoodDark");
        float FU = Mathf.Max(0.5f, ftile.x);
        for (float x = x0 + FU / 2; x < W / 2; x += FU)
            for (float z = z0 + FU / 2; z < D / 2; z += FU)
            {
                Spawn(V + "Floor_WoodDark", new Vector3(x, 0, z));
                Spawn(V + "Floor_WoodLight", new Vector3(x, WallHeight, z));  // ceiling boards
            }
        BoxCollider(new Vector3(0, -0.05f, 0), new Vector3(W, 0.1f, D));

        // perimeter walls — north gets two windows, south the door, west the hearth's brick run
        for (int i = 0; i < nx; i++)
        {
            float x = x0 + U * (i + 0.5f);
            bool win = (i == 1 || i == nx - 2);
            Spawn(V + (win ? "Wall_Plaster_Window_Wide_Flat" : "Wall_Plaster_WoodGrid"),
                  new Vector3(x, 0, D / 2), 0);
            if (win) Pane(new Vector3(x, WallHeight * 0.55f, D / 2 - 0.12f), new Vector3(1.6f, 1.1f, 0.05f));
            bool door = i == nx / 2;
            Spawn(V + (door ? "Wall_Plaster_Door_Round" : "Wall_Plaster_Straight"),
                  new Vector3(x, 0, -D / 2), 180);
            if (door)
            {
                var d = Spawn(V + "Door_1_Round", new Vector3(x + 0.02f, 0, -D / 2), 180);
                WarrantAnchor = new GameObject("warrant.anchor").transform;
                WarrantAnchor.SetParent(root, false);
                WarrantAnchor.position = new Vector3(x, 1.5f, -D / 2 + 0.15f);
            }
        }
        for (int j = 0; j < nz; j++)
        {
            float z = z0 + U * (j + 0.5f);
            bool win = j == nz - 1;
            Spawn(V + (win ? "Wall_Plaster_Window_Wide_Flat" : "Wall_Plaster_Straight"),
                  new Vector3(W / 2, 0, z), -90);
            if (win) Pane(new Vector3(W / 2 - 0.12f, WallHeight * 0.55f, z), new Vector3(0.05f, 1.1f, 1.6f));
            Spawn(V + (j == nz / 2 ? "Wall_UnevenBrick_Straight" : "Wall_Plaster_WoodGrid"),
                  new Vector3(-W / 2, 0, z), 90);
        }
        // wall colliders (thin boxes, full height)
        BoxCollider(new Vector3(0, WallHeight / 2, D / 2), new Vector3(W, WallHeight, 0.3f));
        BoxCollider(new Vector3(0, WallHeight / 2, -D / 2), new Vector3(W, WallHeight, 0.3f));
        BoxCollider(new Vector3(W / 2, WallHeight / 2, 0), new Vector3(0.3f, WallHeight, D));
        BoxCollider(new Vector3(-W / 2, WallHeight / 2, 0), new Vector3(0.3f, WallHeight, D));

        // THE HEARTH (west wall center): brick breast + logs + hanging pot; the light is Bootstrap's
        var hearthPos = new Vector3(-W / 2 + 0.55f, 0, 0);
        Spawn(P + "Anvil_Log", hearthPos + new Vector3(0.1f, 0.05f, 0));
        Spawn(P + "Cauldron", hearthPos + new Vector3(0.15f, 0.1f, 0.35f));
        BoxCollider(hearthPos + Vector3.up * 0.5f, new Vector3(1.0f, 1.0f, 1.6f));

        // THE BAR (east side, in front of the window bay): two workbenches + bottles behind
        var barPos = new Vector3(W / 2 - 1.6f, 0, D / 4);
        Spawn(P + "Workbench_Drawers", barPos, -90);
        Spawn(P + "Workbench_Drawers", barPos + new Vector3(0, 0, -1.1f), -90);
        Spawn(P + "Shelf_Small_Bottles", new Vector3(W / 2 - 0.15f, 1.5f, D / 4), -90);
        Spawn(P + "Barrel", new Vector3(W / 2 - 0.6f, 0, D / 4 + 1.4f));
        Spawn(P + "Mug", barPos + new Vector3(-0.1f, 1.02f, 0.2f));
        Spawn(P + "Bottle_1", barPos + new Vector3(0.1f, 1.02f, -0.3f));
        Spawn(P + "Candle_1", barPos + new Vector3(0, 1.02f, -0.8f));
        BoxCollider(barPos + new Vector3(0, 0.5f, -0.55f), new Vector3(0.9f, 1.1f, 2.3f));

        // A CORNER TABLE (south-west): the long table, stools, dressing
        var tablePos = new Vector3(x0 + 2.2f, 0, z0 + 2.0f);
        Spawn(P + "Table_Large", tablePos, 15);
        Spawn(P + "Stool", tablePos + new Vector3(0.9f, 0, 0.3f));
        Spawn(P + "Stool", tablePos + new Vector3(-0.9f, 0, -0.4f));
        Spawn(P + "Stool", tablePos + new Vector3(0.2f, 0, -0.95f));
        Spawn(P + "Candle_2", tablePos + new Vector3(0, 0.95f, 0));
        Spawn(P + "Book_5", tablePos + new Vector3(0.35f, 0.95f, 0.2f), 40);
        BoxCollider(tablePos + Vector3.up * 0.45f, new Vector3(1.9f, 0.9f, 1.1f));

        // THE WINDOW bay (north-east): bench under the window
        var benchPos = new Vector3(W / 2 - 2.2f, 0, D / 2 - 0.8f);
        Spawn(P + "Bench", benchPos, 180);

        // set dressing
        Spawn(P + "Chandelier", new Vector3(0, WallHeight - 0.35f, 0));
        Spawn(P + "Lantern_Wall", new Vector3(x0 + 0.15f, 1.9f, z0 + 2.0f), 90);
        Spawn(P + "Lantern_Wall", new Vector3(0.8f, 1.9f, -D / 2 + 0.15f), 0);
        Spawn(P + "Banner_1", new Vector3(-1.6f, 2.1f, -D / 2 + 0.12f), 0);
        Spawn(P + "Barrel_Apples", new Vector3(x0 + 0.7f, 0, D / 2 - 0.8f));
        Spawn(P + "Crate_Wooden", new Vector3(x0 + 0.7f, 0, D / 2 - 1.7f), 20);
        Spawn(P + "Peg_Rack", new Vector3(2.2f, 1.6f, -D / 2 + 0.12f), 0);
        Spawn(P + "Shelf_Simple", new Vector3(-W / 2 + 0.15f, 1.6f, -2.2f), 90);
        Spawn(P + "SmallBottles_1", new Vector3(-W / 2 + 0.22f, 1.72f, -2.2f), 90);

        // regions over the real furniture
        Regions.Add("the door", new Vector3(0, 0, -D / 2 + 1.0f));
        Regions.Add("the bar", barPos + new Vector3(-1.1f, 0, -0.4f));
        Regions.Add("the hearth", hearthPos + new Vector3(1.1f, 0, 0));
        Regions.Add("a corner table", tablePos + new Vector3(0.8f, 0, 0.8f));
        Regions.Add("the window", benchPos + new Vector3(-0.5f, 0, -0.9f));
        Regions.Add("the middle of the taproom", new Vector3(0, 0, 0.3f));
    }

    /// An emissive pane inside a window opening — the storm made visible, and the surface
    /// lightning arrives through (StormAudio drives the emission).
    static void Pane(Vector3 pos, Vector3 size)
    {
        var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
        Object.Destroy(go.GetComponent<Collider>());
        go.name = "windowpane";
        go.transform.SetParent(root, false);
        go.transform.position = pos;
        go.transform.localScale = size;
        // TRANSPARENT glass: the storm outside is a view now, not a painting — rain, the flooded
        // crossing, the marsh in the fog. Lightning still spikes the emission (wet-glass glow).
        var m = new Material(Shader.Find("Universal Render Pipeline/Lit")) { name = "Q_pane" };
        m.SetFloat("_Surface", 1);
        m.SetOverrideTag("RenderType", "Transparent");
        m.renderQueue = 3001;
        m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
        m.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
        m.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
        m.SetInt("_ZWrite", 0);
        m.SetColor("_BaseColor", new Color(0.35f, 0.42f, 0.55f, 0.2f));
        m.SetFloat("_Smoothness", 0.92f);
        m.EnableKeyword("_EMISSION");
        m.SetColor("_EmissionColor", new Color(0.05f, 0.07f, 0.1f));
        go.GetComponent<Renderer>().material = m;
        WindowPanes.Add(go.GetComponent<Renderer>().material);
    }
}
