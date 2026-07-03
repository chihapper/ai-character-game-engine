"""Runs INSIDE the editor (via drive.py): measure the tavern for region anchors.
Actors are generically named — search editor LABELS and static-mesh ASSET names."""
import unreal

actors = unreal.EditorLevelLibrary.get_all_level_actors()
keys = ("bar", "table", "fireplace", "chimney", "door", "stair", "counter", "shelf",
        "bench", "chair", "keg", "barrel")
lines = []
for a in actors:
    label = a.get_actor_label().lower()
    meshes = []
    for c in a.get_components_by_class(unreal.StaticMeshComponent):
        if c.static_mesh:
            meshes.append(c.static_mesh.get_name())
    hay = label + " " + " ".join(m.lower() for m in meshes)
    if any(k in hay for k in keys):
        p = a.get_actor_location()
        lines.append("%s [%s]: %.0f, %.0f, %.0f" %
                     (a.get_actor_label(), ",".join(meshes[:2]), p.x, p.y, p.z))
unreal.log("TAVERN MEASURE v2 (%d hits of %d actors) map=%s" %
           (len(lines), len(actors), unreal.EditorLevelLibrary.get_editor_world().get_name()))
for line in sorted(lines)[:55]:
    unreal.log(line)
