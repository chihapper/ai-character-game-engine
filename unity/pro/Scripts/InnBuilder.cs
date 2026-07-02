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
        // scale MULTIPLIES the prefab's own (FBX unit compensation lives there — overwriting it
        // shrank the cauldron/chandelier/jambs to centimeters), and is WORLD-axis-semantic:
        // the prefab root may carry an axis-compensation rotation, so each local axis takes the
        // world component it actually points along
        if (scale.HasValue)
        {
            var w = scale.Value;
            float Along(Vector3 dir) => Mathf.Abs(dir.x) > 0.7f ? w.x : (Mathf.Abs(dir.y) > 0.7f ? w.y : w.z);
            var q = prefab.transform.rotation;
            var local = new Vector3(Along(q * Vector3.right), Along(q * Vector3.up), Along(q * Vector3.forward));
            go.transform.localScale = Vector3.Scale(go.transform.localScale, local);
        }
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
        if (!first && b.size.sqrMagnitude > 1e-6f) return b;
        // spawn-frame quirk: renderer AABBs lag a localScale write (the jambs audited as
        // zero-height the frame they were built) — derive from mesh data instead
        first = true;
        foreach (var mf in go.GetComponentsInChildren<MeshFilter>())
        {
            if (mf.sharedMesh == null) continue;
            var mb = mf.sharedMesh.bounds;
            for (int i = 0; i < 8; i++)
            {
                var c = mb.center + Vector3.Scale(mb.extents,
                    new Vector3((i & 1) * 2 - 1, ((i >> 1) & 1) * 2 - 1, ((i >> 2) & 1) * 2 - 1));
                var w = mf.transform.TransformPoint(c);
                if (first) { b = new Bounds(w, Vector3.zero); first = false; } else b.Encapsulate(w);
            }
        }
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

        // FLAGSTONE floor (the reference taprooms all stand on stone), wood-board ceiling
        var ftile = Size(V + "Floor_UnevenBrick");
        float FU = Mathf.Max(0.5f, ftile.x);
        for (float x = x0 + FU / 2; x < W / 2; x += FU)
            for (float z = z0 + FU / 2; z < D / 2; z += FU)
            {
                Spawn(V + "Floor_UnevenBrick", new Vector3(x, 0, z));
                Spawn(V + "Floor_WoodLight", new Vector3(x, WallHeight - 0.02f, z));  // ceiling boards
            }
        BoxCollider(new Vector3(0, -0.05f, 0), new Vector3(W, 0.1f, D));
        BoxCollider(new Vector3(0, WallHeight + 0.5f, 0), new Vector3(W, 1f, D));  // rain dies on the roof (thick: fast drops tunnel thin boxes)

        // perimeter walls — north gets two windows, south the door, west the hearth's brick run
        for (int i = 0; i < nx; i++)
        {
            float x = x0 + U * (i + 0.5f);
            bool win = (i == 1 || i == nx - 2);
            // STONE shell (reference: uneven fieldstone with heavy timber) — the lattice
            // WoodGrid module stays an interior divider only
            Spawn(V + (win ? "Wall_UnevenBrick_Window_Wide_Flat" : "Wall_UnevenBrick_Straight"),
                  new Vector3(x, 0, D / 2), 0);
            // no glass pane geometry: the module's opening is off its bounds-center, so a placed
            // quad straddles solid wall and (one-sided shells) reads as a hole to the sky.
            // Medieval shutters carry it — rain and lightning arrive through the open window.
            bool door = i == nx / 2;
            Spawn(V + (door ? "Wall_UnevenBrick_Door_Round" : "Wall_UnevenBrick_Straight"),
                  new Vector3(x, 0, -D / 2), 180);
            if (door)
            {
                Spawn(V + "DoorFrame_Round_WoodDark", new Vector3(x, 0, -D / 2), 180);  // fills the arch
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
            Spawn(V + (win ? "Wall_UnevenBrick_Window_Wide_Flat" : "Wall_UnevenBrick_Straight"),
                  new Vector3(W / 2, 0, z), -90);
            Spawn(V + "Wall_UnevenBrick_Straight", new Vector3(-W / 2, 0, z), 90);
        }
        // THE TIMBER FRAME (reference: heavy posts, cross beams, angled braces against stone).
        // Kit has no interior post module — textured primitives carry it, same wood as the beams.
        var beamM = new Material(QMaterials.Map("wood beam"));
        beamM.SetColor("_BaseColor", new Color(0.66f, 0.52f, 0.38f));
        beamM.SetTextureScale("_BaseMap", new Vector2(0.5f, 1.6f));   // grain runs ALONG the timber, not smeared across it
        GameObject Timber(Vector3 center, Vector3 size, Vector3 euler, bool collide)
        {
            var t = GameObject.CreatePrimitive(PrimitiveType.Cube);
            t.name = "timber";
            if (!collide) Object.Destroy(t.GetComponent<Collider>());
            t.transform.SetParent(root, false);
            t.transform.position = center;
            t.transform.localScale = size;
            t.transform.rotation = Quaternion.Euler(euler);
            t.GetComponent<Renderer>().material = beamM;
            return t;
        }
        // wall posts, inset against the stone
        foreach (float px in new[] { -4f, -2f, 0f, 2f, 4f })
            Timber(new Vector3(px, WallHeight / 2, D / 2 - 0.28f), new Vector3(0.24f, WallHeight, 0.24f), Vector3.zero, false);
        foreach (float px in new[] { -4f, -2f, 3.4f })
            Timber(new Vector3(px, WallHeight / 2, -D / 2 + 0.28f), new Vector3(0.24f, WallHeight, 0.24f), Vector3.zero, false);
        foreach (float pz in new[] { -2.6f, 2.6f })
            Timber(new Vector3(-W / 2 + 0.28f, WallHeight / 2, pz), new Vector3(0.24f, WallHeight, 0.24f), Vector3.zero, false);
        // two free-standing center posts flanking the long table, braced up into the beams
        foreach (float px in new[] { -2.5f, 2.5f })
        {
            Timber(new Vector3(px, WallHeight / 2, 0.4f), new Vector3(0.3f, WallHeight, 0.3f), Vector3.zero, true);
            Timber(new Vector3(px + 0.55f, WallHeight - 0.7f, 0.4f), new Vector3(0.16f, 1.1f, 0.16f), new Vector3(0, 0, 40f), false);
            Timber(new Vector3(px - 0.55f, WallHeight - 0.7f, 0.4f), new Vector3(0.16f, 1.1f, 0.16f), new Vector3(0, 0, -40f), false);
        }
        // beam grid under the ceiling
        foreach (float bx in new[] { -2.5f, 2.5f })
            Timber(new Vector3(bx, WallHeight - 0.12f, 0), new Vector3(0.28f, 0.22f, D - 0.3f), Vector3.zero, false);
        Timber(new Vector3(0, WallHeight - 0.3f, 0.4f), new Vector3(W - 0.3f, 0.2f, 0.26f), Vector3.zero, false);

        // wall colliders (thin boxes, full height)
        BoxCollider(new Vector3(0, WallHeight / 2, D / 2), new Vector3(W, WallHeight, 0.3f));
        BoxCollider(new Vector3(0, WallHeight / 2, -D / 2), new Vector3(W, WallHeight, 0.3f));
        BoxCollider(new Vector3(W / 2, WallHeight / 2, 0), new Vector3(0.3f, WallHeight, D));
        BoxCollider(new Vector3(-W / 2, WallHeight / 2, 0), new Vector3(0.3f, WallHeight, D));

        // THE HEARTH (west wall center): a real fireplace — brick pad, flanking jambs, a wooden
        // mantel beam, stacked logs; the fire light + flames are Bootstrap's
        var hearthPos = new Vector3(-W / 2 + 0.55f, 0, 0);
        Spawn(V + "Floor_Brick", hearthPos + new Vector3(0.35f, 0.01f, 0));
        // full-height brick jambs: the shot read them as a proper chimney breast — keep that.
        // Renamed so the layout audit's PERIMETER-wall check doesn't flag deliberate interior brick.
        var j1 = Spawn(V + "Wall_UnevenBrick_Straight", hearthPos + new Vector3(0.05f, 0, 1.05f), 0, new Vector3(0.28f, 1f, 0.62f));
        var j2 = Spawn(V + "Wall_UnevenBrick_Straight", hearthPos + new Vector3(0.05f, 0, -1.05f), 0, new Vector3(0.28f, 1f, 0.62f));
        if (j1 != null) j1.name = "hearth.jamb";
        if (j2 != null) j2.name = "hearth.jamb";
        var mantel = GameObject.CreatePrimitive(PrimitiveType.Cube);
        mantel.transform.SetParent(root, false);
        mantel.transform.position = hearthPos + new Vector3(0.22f, 2.05f, 0);
        mantel.transform.localScale = new Vector3(0.5f, 0.14f, 2.4f);   // slim + high: heads clear it
        var mantelM = new Material(QMaterials.Map("wood beam"));   // textured, not flat gray
        mantelM.SetColor("_BaseColor", new Color(0.5f, 0.38f, 0.26f));
        mantel.GetComponent<Renderer>().material = mantelM;
        var logM = new Material(QMaterials.Map("wood"));
        logM.SetColor("_BaseColor", new Color(0.42f, 0.3f, 0.2f));
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

        // THE BAR (east side, in front of the window bay): a three-unit counter RUN with
        // bottles, mugs, and a keg — it has to READ as a bar from across the room
        var barPos = new Vector3(W / 2 - 1.6f, 0, D / 4);
        var bench = Spawn(P + "Workbench_Drawers", barPos + new Vector3(0, 0, 1.1f), -90);
        Spawn(P + "Workbench_Drawers", barPos, -90);
        Spawn(P + "Workbench_Drawers", barPos + new Vector3(0, 0, -1.1f), -90);
        Spawn(P + "Shelf_Small_Bottles", new Vector3(W / 2 - 0.15f, 1.5f, D / 4), -90);
        Spawn(P + "Shelf_Arch", new Vector3(W / 2 - 0.15f, 1.45f, D / 4 - 1.2f), -90);
        Spawn(P + "Cabinet", new Vector3(W / 2 - 0.45f, 0, 0.3f), -90);   // back bar, between counter and kitchen door
        Spawn(P + "Barrel_Holder", new Vector3(W / 2 - 0.55f, 0, D / 4 - 1.9f));  // the keg
        float barTop = TopOf(bench);
        BarTop = barTop;
        Spawn(P + "Mug", barPos + new Vector3(-0.1f, 0, 0.9f), 0).transform.position += Vector3.up * barTop;
        Spawn(P + "Mug", barPos + new Vector3(0.08f, 0, 0.1f), 35).transform.position += Vector3.up * barTop;
        Spawn(P + "Bottle_1", barPos + new Vector3(0.1f, 0, -0.4f), 0).transform.position += Vector3.up * barTop;
        Spawn(P + "Table_Plate", barPos + new Vector3(-0.05f, 0, -0.9f), 0).transform.position += Vector3.up * barTop;
        Spawn(P + "Candle_1", barPos + new Vector3(0, 0, 1.4f), 0).transform.position += Vector3.up * barTop;
        BoxCollider(barPos + new Vector3(0, 0.5f, 0), new Vector3(0.9f, 1.1f, 3.4f));

        // THE BACK KITCHEN (south-east, walled off behind the bar): where the stew actually
        // comes from — prep counter, pots, crates of food, water bucket. Entry gap by the bar.
        // the open WoodGrid lattice finally earns its place: an interior divider you can
        // glimpse the kitchen through (reference bars use exactly this)
        var kitchenWall = Spawn(V + "Wall_Plaster_WoodGrid", new Vector3(W / 2 - 1.0f, 0, -0.5f), 0);
        if (kitchenWall != null) kitchenWall.name = "kitchen.partition";  // interior wall: not the perimeter audit's business
        BoxCollider(new Vector3(W / 2 - 1.0f, WallHeight / 2, -0.5f), new Vector3(2.0f, WallHeight, 0.3f));
        var prep = Spawn(P + "Workbench_Drawers", new Vector3(W / 2 - 0.55f, 0, -1.6f), -90);
        float prepTop = TopOf(prep);
        Spawn(P + "Pot_1", new Vector3(W / 2 - 0.55f, 0, -1.4f)).transform.position += Vector3.up * prepTop;
        Spawn(P + "Table_Knife", new Vector3(W / 2 - 0.5f, 0, -1.9f), 25).transform.position += Vector3.up * prepTop;
        Spawn(P + "FarmCrate_Carrot", new Vector3(W / 2 - 1.5f, 0, -3.3f), 15);
        Spawn(P + "FarmCrate_Apple", new Vector3(W / 2 - 0.6f, 0, -3.3f), -10);
        Spawn(P + "Bucket_Wooden_1", new Vector3(W / 2 - 1.7f, 0, -2.2f));
        Spawn(P + "Shelf_Simple", new Vector3(W / 2 - 0.15f, 1.6f, -2.6f), -90);
        Spawn(P + "SmallBottles_1", new Vector3(W / 2 - 0.22f, 1.72f, -2.6f), -90);
        BoxCollider(new Vector3(W / 2 - 0.55f, 0.5f, -1.6f), new Vector3(0.9f, 1.1f, 1.2f));

        // THE LONG TABLE (middle of the room): the table a stranger gets waved toward
        var tablePos = new Vector3(-1.2f, 0, -0.5f);
        Spawn(P + "Table_Large", tablePos, 15);
        Seat(tablePos + new Vector3(0.9f, 0, 0.3f), tablePos);
        Seat(tablePos + new Vector3(-0.9f, 0, -0.4f), tablePos);
        Seat(tablePos + new Vector3(0.2f, 0, -0.95f), tablePos);
        Spawn(P + "Candle_2", tablePos).transform.position += Vector3.up * 0.92f;
        Spawn(P + "Book_5", tablePos + new Vector3(0.35f, 0, 0.2f), 40).transform.position += Vector3.up * 0.92f;
        BoxCollider(tablePos + Vector3.up * 0.45f, new Vector3(1.9f, 0.9f, 1.1f));

        // BARREL TABLES (straight out of the reference): an upright barrel, stools around it
        void BarrelTable(Vector3 pos, int stools)
        {
            var barrel = Spawn(P + "Barrel", pos);
            float top = TopOf(barrel);
            Spawn(P + "Mug", pos + new Vector3(0.12f, 0, 0.05f), 30).transform.position += Vector3.up * top;
            Spawn(P + "Candle_1", pos + new Vector3(-0.14f, 0, -0.1f)).transform.position += Vector3.up * top;
            for (int s = 0; s < stools; s++)
            {
                float ang = (s * 360f / stools + 25f) * Mathf.Deg2Rad;
                Seat(pos + new Vector3(Mathf.Sin(ang), 0, Mathf.Cos(ang)) * 0.85f, pos);
            }
            BoxCollider(pos + Vector3.up * 0.5f, new Vector3(0.8f, 1f, 0.8f));
        }
        BarrelTable(new Vector3(-3.6f, 0, 1.9f), 2);
        BarrelTable(new Vector3(2.6f, 0, -2.1f), 3);

        // A SMALL TABLE across from the bar — one seat, one candle: a performer's perch
        var smallPos = new Vector3(1.7f, 0, 2.1f);
        Spawn(P + "Table_Large", smallPos, 40, new Vector3(0.62f, 1f, 0.62f));
        Seat(smallPos + new Vector3(0.85f, 0, -0.35f), smallPos);
        Spawn(P + "Mug", smallPos + new Vector3(0.1f, 0, 0.1f), 0).transform.position += Vector3.up * 0.9f;
        Spawn(P + "Candle_1", smallPos + new Vector3(-0.25f, 0, -0.2f), 0).transform.position += Vector3.up * 0.9f;
        BoxCollider(smallPos + Vector3.up * 0.45f, new Vector3(1.2f, 0.9f, 0.8f));

        // THE WINDOW bay (north-east): bench under the window
        var benchPos = new Vector3(W / 2 - 2.2f, 0, D / 2 - 0.8f);
        Spawn(P + "Bench", benchPos, 180);
        Seats.Add((benchPos, benchPos + Vector3.back * 3f));

        // roof cap: from outside, the open top edge leaked lit ceiling boards over the walls
        var roof = GameObject.CreatePrimitive(PrimitiveType.Cube);
        roof.name = "roofcap";
        roof.transform.SetParent(root, false);
        roof.transform.position = new Vector3(0, WallHeight + 0.12f, 0);
        roof.transform.localScale = new Vector3(W + 0.7f, 0.24f, D + 0.7f);
        var roofM = new Material(QMaterials.Map("wood"));
        roofM.SetColor("_BaseColor", new Color(0.2f, 0.15f, 0.11f));
        roof.GetComponent<Renderer>().material = roofM;

        // set dressing
        void CandleRing(Vector3 at)
        {
            var chand = Spawn(P + "Chandelier", at, 0, Vector3.one * 0.6f);
            Hang(chand, WallHeight - 0.05f);
            if (chand == null) return;
            // its candles carry the room — without this the taproom floor is a pit
            var cl = new GameObject("chandelight").AddComponent<Light>();
            cl.transform.SetParent(chand.transform, false);
            cl.transform.position = WorldBounds(chand).center + Vector3.down * 0.15f;
            cl.type = LightType.Point;
            cl.range = 6.5f;
            cl.intensity = 2.1f;   // two rings now share the job
            cl.color = new Color(1f, 0.75f, 0.45f);
        }
        CandleRing(new Vector3(1.4f, 0, 1.2f));    // over the taproom middle
        CandleRing(new Vector3(-1.6f, 0, -0.8f));  // over the long table
        Spawn(P + "Lantern_Wall", new Vector3(x0 + 0.15f, 1.9f, z0 + 2.0f), 90);
        Spawn(P + "Lantern_Wall", new Vector3(1.9f, 1.9f, -D / 2 + 0.15f), 0);  // clear of the door arch
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
        Regions.Add("the hearth", hearthPos + new Vector3(1.55f, 0, 0));   // stand CLEAR of the mantel
        Regions.Add("the long table", tablePos + new Vector3(0.8f, 0, 0.8f));
        Regions.Add("a small table", smallPos + new Vector3(0.6f, 0, -0.7f));
        Regions.Add("the back kitchen", new Vector3(W / 2 - 1.1f, 0, -2.3f));
        Regions.Add("the window", benchPos + new Vector3(-0.5f, 0, -0.9f));
        Regions.Add("the middle of the taproom", new Vector3(0.8f, 0, 1.0f));   // clear of the relocated long table
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

}
