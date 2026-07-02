// The bridge between EDITOR-BAKED worlds and the runtime: when the world is built into the scene
// ahead of time (Ferry > Build World Into Scene) this component carries the registries the code
// normally fills at runtime — region anchors, seats, window panes, the warrant anchor — so
// Bootstrap can RESTORE them instead of rebuilding, and every hand-adjustment you make in the
// editor is exactly what plays.
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

public class WorldMarker : MonoBehaviour
{
    public List<string> regionNames = new();
    public List<Vector3> regionPositions = new();
    public List<Vector3> seatPositions = new();
    public List<Vector3> seatFacings = new();
    public List<Renderer> panes = new();
    public Transform warrantAnchor;
    public float wallHeight = 3f;

    public void Capture()
    {
        regionNames = Regions.Names.ToList();
        regionPositions = regionNames.Select(Regions.Anchor).ToList();
        seatPositions = InnBuilder.Seats.Select(s => s.pos).ToList();
        seatFacings = InnBuilder.Seats.Select(s => s.face).ToList();
        panes = FindObjectsByType<Renderer>(FindObjectsSortMode.None)
                .Where(r => r.gameObject.name == "windowpane").ToList();
        warrantAnchor = InnBuilder.WarrantAnchor;
        wallHeight = InnBuilder.WallHeight;
    }

    public void Restore()
    {
        for (int i = 0; i < regionNames.Count; i++)
            Regions.Add(regionNames[i], regionPositions[i]);
        InnBuilder.RestoreFromMarker(
            seatPositions.Zip(seatFacings, (p, f) => (p, f)).ToList(),
            panes.Where(p => p != null).Select(p => p.material).ToList(),
            warrantAnchor, wallHeight);
    }
}
