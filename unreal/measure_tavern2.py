"""Second pass: only tables, doors, fireplace, stairs."""
import unreal

actors = unreal.EditorLevelLibrary.get_all_level_actors()
keys = ("table", "door", "fire", "chimney", "stair")
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
        lines.append("%s: %.0f, %.0f, %.0f" % (a.get_actor_label(), p.x, p.y, p.z))
unreal.log("MEASURE2 (%d)" % len(lines))
for line in sorted(lines)[:40]:
    unreal.log(line)
