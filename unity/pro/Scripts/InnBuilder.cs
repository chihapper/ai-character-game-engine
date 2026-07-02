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
    public static float BarTop { get; private set; } = 1.0f;
    public static readonly List<(Vector3 pos, Vector3 face)> Seats = new();  // where a body can SIT
    public static Transform WarrantAnchor { get; private set; }
    public static float WallHeight { get; private set; } = 3f;

    static Transform root;

    /// A world baked in the EDITOR restores its registries here instead of rebuilding.
    public static void RestoreFromMarker(List<(Vector3 pos, Vector3 face)> seats,
                                         List<Material> panes, Transform warrant, float wallH)
    {
        Seats.Clear(); Seats.AddRange(seats);
        WindowPanes.Clear(); WindowPanes.AddRange(panes);
        WarrantAnchor = warrant;
        WallHeight = wallH;
    }

    // Pieces have arbitrary pivots (the MegaKit walls pivot at CENTER — placed by pivot they
    // sink to their waists, which collapsed the whole inn). Every spawn is GROUNDED by its
    // measured world bounds instead: pos.y becomes where the piece's BASE sits.
    static GameObject Spawn(string path, Vector3 pos, float yRot = 0, Vector3? scale = null)
    {
        var prefab = Resources.Load<GameObject>(path);
        if (prefab == null) { Debug.LogWarning($"InnBuilder: missing prefab {path}"); return null; }
        // FBX from Blender bakes a -90X axis-compensation into the prefab ROOT rotation;
        // Instantiate with an absolute rotation WIPES it and lays every piece flat (the audit's
        // 'wall vertical span 0.0..0.4'). Compose our yaw WITH the prefab's own rotation.
        var go = Object.Instantiate(prefab, pos,
            Quaternion.Euler(0, yRot, 0) * prefab.transform.rotation, root);
        if (scale.HasValue) go.transform.localScale = scale.Value;
        QMaterials.Apply(go);
        var b = WorldBounds(go);
        go.transform.position += new Vector3(pos.x - b.center.x, pos.y - b.min.y, pos.z - b.center.z);
        return go;
    }

    static Bounds WorldBounds(GameObject go)
    {
        var b = new Bounds(go.transform.position, Vector3.zero); bool first = true;
        foreach (var r in go.GetComponentsInChildren<Renderer>())
        { if (first) { b = r.bounds; first = false; } else b.Encapsulate(r.bounds); }
        return b;
    }

    static void Ground(GameObject go, float baseY)
    {
        if (go == null) return;
        var b = WorldBounds(go);
        go.transform.position += Vector3.up * (baseY - b.min.y);
    }

    static void Hang(GameObject go, float topY)
    {
        if (go == null) return;
        var b = WorldBounds(go);
        go.transform.position += Vector3.up * (topY - b.max.y);
    }

    static float TopOf(GameObject go) => go == null ? 0f : WorldBounds(go).max.y;

    static Vector3 Size(string path)
    {
        // measure a real INSTANCE (with its axis compensation applied) — raw prefab bounds lie
        var prefab = Resources.Load<GameObject>(path);
        if (prefab == null) return Vector3.one * 2;
        var probe = Object.Instantiate(prefab, new Vector3(0, -500, 0), prefab.transform.rotation);
        var b = new Bounds(probe.transform.position, Vector3.zero);
        bool first = true;
        foreach (var r in probe.GetComponentsInChildren<Renderer>())
        { if (first) { b = r.bounds; first = false; } else b.Encapsulate(r.bounds); }
        if (Application.isPlaying) Object.Destroy(probe); else Object.DestroyImmediate(probe);
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
        WindowPanes.Clear();   // statics survive the [R] scene reload — the registries must not
        Seats.Clear();
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
                Spawn(V + "Floor_WoodLight", new Vector3(x, WallHeight - 0.02f, z));  // ceiling boards
            }
        BoxCollider(new Vector3(0, -0.05f, 0), new Vector3(W, 0.1f, D));

        // perimeter walls — north gets two windows, south the door, west the hearth's brick run
        for (int i = 0; i < nx; i++)
        {
            float x = x0 + U * (i + 0.5f);
            bool win = (i == 1 || i == nx - 2);
            Spawn(V + (win ? "Wall_Plaster_Window_Wide_Flat" : "Wall_Plaster_WoodGrid"),
                  new Vector3(x, 0, D / 2), 0);
            if (win)
            {
                var ww = root.GetChild(root.childCount - 1).gameObject;   // the window wall just spawned
                var wb = WorldBounds(ww);
                Pane(new Vector3(wb.center.x, WallHeight * 0.55f, D / 2 - 0.12f), new Vector3(1.7f, 1.2f, 0.05f));
            }
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
            if (win)
            {
                var ww = root.GetChild(root.childCount - 1).gameObject;
                var wb = WorldBounds(ww);
                Pane(new Vector3(W / 2 - 0.12f, WallHeight * 0.55f, wb.center.z), new Vector3(0.05f, 1.2f, 1.7f));
            }
            Spawn(V + (j == nz / 2 ? "Wall_UnevenBrick_Straight" : "Wall_Plaster_WoodGrid"),
                  new Vector3(-W / 2, 0, z), 90);
        }
        // wall colliders (thin boxes, full height)
        BoxCollider(new Vector3(0, WallHeight / 2, D / 2), new Vector3(W, WallHeight, 0.3f));
        BoxCollider(new Vector3(0, WallHeight / 2, -D / 2), new Vector3(W, WallHeight, 0.3f));
        BoxCollider(new Vector3(W / 2, WallHeight / 2, 0), new Vector3(0.3f, WallHeight, D));
        BoxCollider(new Vector3(-W / 2, WallHeight / 2, 0), new Vector3(0.3f, WallHeight, D));

        // THE HEARTH (west wall center): a real fireplace — brick pad, flanking jambs, a wooden
        // mantel beam, stacked logs; the fire light + flames are Bootstrap's
        var hearthPos = new Vector3(-W / 2 + 0.55f, 0, 0);
        Spawn(V + "Floor_Brick", hearthPos + new Vector3(0.35f, 0.01f, 0));
        Spawn(V + "Wall_UnevenBrick_Straight", hearthPos + new Vector3(0.05f, 0, 1.05f), 0, new Vector3(0.28f, 0.62f, 1f));
        Spawn(V + "Wall_UnevenBrick_Straight", hearthPos + new Vector3(0.05f, 0, -1.05f), 0, new Vector3(0.28f, 0.62f, 1f));
        var mantel = GameObject.CreatePrimitive(PrimitiveType.Cube);
        mantel.transform.SetParent(root, false);
        mantel.transform.position = hearthPos + new Vector3(0.3f, 1.95f, 0);
        mantel.transform.localScale = new Vector3(0.75f, 0.16f, 2.5f);
        mantel.GetComponent<Renderer>().material = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        mantel.GetComponent<Renderer>().material.SetColor("_BaseColor", new Color(0.32f, 0.24f, 0.17f));
        var logM = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        logM.SetColor("_BaseColor", new Color(0.2f, 0.14f, 0.1f));
        for (int li = 0; li < 3; li++)
        {
            var log = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            Object.Destroy(log.GetComponent<Collider>());
            log.transform.SetParent(root, false);
            log.transform.position = hearthPos + new Vector3(0.15f + (li == 2 ? 0.08f : 0), 0.12f + li / 2 * 0.16f, -0.25f + li * 0.25f);
            log.transform.localScale = new Vector3(0.16f, 0.35f, 0.16f);
            log.transform.rotation = Quaternion.Euler(90, li * 25f, 0);
            log.GetComponent<Renderer>().material = logM;
        }
        Spawn(P + "Cauldron", hearthPos + new Vector3(0.5f, 0, 1.35f), 0, Vector3.one * 0.8f);  // beside, not IN it
        BoxCollider(hearthPos + Vector3.up * 0.5f, new Vector3(1.0f, 1.0f, 2.4f));

        // THE BAR (east side, in front of the window bay): two workbenches + bottles behind
        var barPos = new Vector3(W / 2 - 1.6f, 0, D / 4);
        var bench = Spawn(P + "Workbench_Drawers", barPos, -90);
        Spawn(P + "Workbench_Drawers", barPos + new Vector3(0, 0, -1.1f), -90);
        Spawn(P + "Shelf_Small_Bottles", new Vector3(W / 2 - 0.15f, 1.5f, D / 4), -90);
        Spawn(P + "Barrel", new Vector3(W / 2 - 0.6f, 0, D / 4 + 1.4f));
        float barTop = TopOf(bench);
        BarTop = barTop;
        Spawn(P + "Mug", barPos + new Vector3(-0.1f, 0, 0.2f), 0).transform.position += Vector3.up * barTop;
        Spawn(P + "Bottle_1", barPos + new Vector3(0.1f, 0, -0.3f), 0).transform.position += Vector3.up * barTop;
        Spawn(P + "Candle_1", barPos + new Vector3(0, 0, -0.8f), 0).transform.position += Vector3.up * barTop;
        BoxCollider(barPos + new Vector3(0, 0.5f, -0.55f), new Vector3(0.9f, 1.1f, 2.3f));

        // A CORNER TABLE (south-west): the long table, stools, dressing
        var tablePos = new Vector3(x0 + 2.2f, 0, z0 + 2.0f);
        Spawn(P + "Table_Large", tablePos, 15);
        Seat(tablePos + new Vector3(0.9f, 0, 0.3f), tablePos);
        Seat(tablePos + new Vector3(-0.9f, 0, -0.4f), tablePos);
        Seat(tablePos + new Vector3(0.2f, 0, -0.95f), tablePos);
        Spawn(P + "Candle_2", tablePos).transform.position += Vector3.up * 0.92f;
        Spawn(P + "Book_5", tablePos + new Vector3(0.35f, 0, 0.2f), 40).transform.position += Vector3.up * 0.92f;
        BoxCollider(tablePos + Vector3.up * 0.45f, new Vector3(1.9f, 0.9f, 1.1f));

        // THE WINDOW bay (north-east): bench under the window
        var benchPos = new Vector3(W / 2 - 2.2f, 0, D / 2 - 0.8f);
        Spawn(P + "Bench", benchPos, 180);
        Seats.Add((benchPos, benchPos + Vector3.back * 3f));

        // set dressing
        Hang(Spawn(P + "Chandelier", new Vector3(0, 0, 0), 0, Vector3.one * 0.6f), WallHeight - 0.05f);
        Spawn(P + "Lantern_Wall", new Vector3(x0 + 0.15f, 1.9f, z0 + 2.0f), 90);
        Spawn(P + "Lantern_Wall", new Vector3(0.8f, 1.9f, -D / 2 + 0.15f), 0);
        Spawn(P + "Banner_1", new Vector3(-1.6f, 2.1f, -D / 2 + 0.12f), 0);
        Spawn(P + "Barrel_Apples", new Vector3(x0 + 0.7f, 0, D / 2 - 0.8f));
        Spawn(P + "Crate_Wooden", new Vector3(x0 + 0.7f, 0, D / 2 - 1.7f), 20);
        Spawn(P + "Peg_Rack", new Vector3(2.2f, 1.6f, -D / 2 + 0.12f), 0);
        Spawn(P + "Shelf_Simple", new Vector3(-W / 2 + 0.15f, 1.6f, -2.2f), 90);
        Spawn(P + "SmallBottles_1", new Vector3(-W / 2 + 0.22f, 1.72f, -2.2f), 90);

        // regions over the real furniture
        VerifyLayout(W, D);

        Regions.Add("the door", new Vector3(0, 0, -D / 2 + 1.0f));
        Regions.Add("the bar", barPos + new Vector3(-1.1f, 0, -0.4f));
        Regions.Add("the hearth", hearthPos + new Vector3(1.1f, 0, 0));
        Regions.Add("a corner table", tablePos + new Vector3(0.8f, 0, 0.8f));
        Regions.Add("the window", benchPos + new Vector3(-0.5f, 0, -0.9f));
        Regions.Add("the middle of the taproom", new Vector3(0, 0, 0.3f));
    }

    static void Seat(Vector3 pos, Vector3 faceToward)
    {
        Spawn(P + "Stool", pos);
        Seats.Add((pos, faceToward));
    }

    /// Layout audit — runs every build, writes the measured room into the log. A wall whose
    /// bounds-center strays from its perimeter line, a floor with holes, a door off its line:
    /// all reported as LAYOUT FAIL lines (grep-able), never silently trusted.
    static void VerifyLayout(float W, float D)
    {
        int fails = 0;
        var floorMin = new Vector2(float.MaxValue, float.MaxValue);
        var floorMax = new Vector2(float.MinValue, float.MinValue);
        foreach (Transform t in root)
        {
            var go = t.gameObject;
            if (!go.name.Contains("(Clone)")) continue;
            var b = WorldBounds(go);
            if (go.name.StartsWith("Floor_") && b.center.y < WallHeight / 2)
            {
                floorMin = Vector2.Min(floorMin, new Vector2(b.min.x, b.min.z));
                floorMax = Vector2.Max(floorMax, new Vector2(b.max.x, b.max.z));
            }
            if (go.name.StartsWith("Wall_"))
            {
                float dN = Mathf.Abs(b.center.z - D / 2), dS = Mathf.Abs(b.center.z + D / 2);
                float dE = Mathf.Abs(b.center.x - W / 2), dW = Mathf.Abs(b.center.x + W / 2);
                float nearest = Mathf.Min(dN, dS, dE, dW);
                if (nearest > 0.6f)
                { fails++; Debug.Log($"LAYOUT FAIL wall {go.name} center={b.center:F1} is {nearest:F1}m off every perimeter line"); }
                if (b.min.y > 0.3f || b.max.y < WallHeight * 0.8f)
                { fails++; Debug.Log($"LAYOUT FAIL wall {go.name} vertical span {b.min.y:F1}..{b.max.y:F1} (wallH={WallHeight:F1})"); }
            }
            if (go.name.StartsWith("Door_1") && Mathf.Abs(b.center.z + D / 2) > 0.8f)
            { fails++; Debug.Log($"LAYOUT FAIL door center={b.center:F1} not on the south line z={-D / 2:F1}"); }
        }
        float gapX = (floorMax.x - floorMin.x) - W, gapZ = (floorMax.y - floorMin.y) - D;
        if (Mathf.Abs(gapX) > 1.2f || Mathf.Abs(gapZ) > 1.2f)
        { fails++; Debug.Log($"LAYOUT FAIL floor covers {floorMax.x - floorMin.x:F1}x{floorMax.y - floorMin.y:F1} vs room {W:F1}x{D:F1}"); }
        Debug.Log(fails == 0
            ? $"LAYOUT OK room {W:F1}x{D:F1}m wallH={WallHeight:F1} floor {floorMax.x - floorMin.x:F1}x{floorMax.y - floorMin.y:F1}"
            : $"LAYOUT: {fails} FAILS (see above)");
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
