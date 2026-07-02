// The autonomous visual test rig: when autoshot.flag exists in the project root, this waits for
// the world + cast to build, photographs ~10 canonical views (each character up close, hearth,
// bar, door, windows in/out), writes a numeric SCENE X-RAY (positions, bounds, meshes, materials,
// rig state), then signals done. The build agent launches Unity, reads the images itself, fixes,
// and relaunches — no human needed in the verification loop.
using System.Collections;
using System.IO;
using System.Linq;
using System.Text;
using UnityEngine;

public class AutoShot : MonoBehaviour
{
    public static string Root => Path.Combine(Application.dataPath, "..");
    static string Dir => Path.Combine(Root, "Screenshots", "auto");

    void Start()
    {
        if (File.Exists(Path.Combine(Root, "autoshot.flag")))
            StartCoroutine(Run());
    }

    IEnumerator Run()
    {
        Directory.CreateDirectory(Dir);
        foreach (var f in Directory.GetFiles(Dir)) File.Delete(f);
        float t0 = Time.time;
        while (NpcAgent.All.Count < 4 && Time.time - t0 < 45f) yield return null;   // session + cast
        yield return new WaitForSeconds(4f);   // outfits, poses, fires settle
        var curtain = FindFirstObjectByType<CurtainUI>();      // late sweep: CurtainUI.Awake also
        if (curtain != null) DestroyImmediate(curtain);        // self-skips under the flag

        var cam = Camera.main;
        var pc = PlayerController.I;
        if (pc != null) pc.enabled = false;
        cam.transform.SetParent(null);
        // inspection fill light: the game scene is deliberately dark — captures need to be
        // READABLE for review; rig-only, never part of the game
        var fill = new GameObject("autoshot.fill").AddComponent<Light>();
        fill.transform.SetParent(cam.transform, false);
        fill.type = LightType.Point; fill.range = 14f; fill.intensity = 1.4f;
        fill.color = new Color(1f, 0.96f, 0.9f);

        IEnumerator Shot(string name, Vector3 pos, Vector3 lookAt)
        {
            cam.transform.position = pos;
            cam.transform.rotation = Quaternion.LookRotation(lookAt - pos);
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(Path.Combine(Dir, name + ".png"));
            yield return new WaitForSeconds(0.35f);   // let the async write land
        }

        foreach (var npc in NpcAgent.All.ToArray())
        {
            var head = npc.transform.position + Vector3.up * 1.45f;
            yield return Shot("npc_" + npc.slug.Split('-')[0],
                npc.transform.position + npc.transform.forward * 2.0f + Vector3.up * 1.5f, head);
        }
        var hearth = Regions.Anchor("the hearth");
        var bar = Regions.Anchor("the bar");
        var door = Regions.Anchor("the door");
        var mid = Regions.Anchor("the middle of the taproom");
        yield return Shot("hearth", hearth + new Vector3(2.6f, 1.6f, 0.6f), hearth + Vector3.up * 0.8f);
        yield return Shot("bar", bar + new Vector3(-2.6f, 1.6f, -0.6f), bar + Vector3.up * 1.0f);
        yield return Shot("door_inside", mid + Vector3.up * 1.6f, door + Vector3.up * 1.2f);
        yield return Shot("room_wide", door + new Vector3(0, 2.0f, 0.6f), mid + Vector3.up * 0.8f);
        yield return Shot("window_inside", mid + new Vector3(0, 1.6f, -1f), mid + new Vector3(1.5f, 1.7f, 4f));
        yield return Shot("exterior_north", new Vector3(0, 2.2f, 12f), new Vector3(0, 1.5f, 4f));
        yield return Shot("exterior_door", door + new Vector3(0.5f, 1.7f, -5f), door + Vector3.up * 1.4f);

        File.WriteAllText(Path.Combine(Dir, "scene_xray.txt"), Xray());
        File.WriteAllText(Path.Combine(Root, "autoshot.done"), "ok");
        Debug.Log("AUTOSHOT complete");
    }

    static string Xray()
    {
        var sb = new StringBuilder();
        sb.AppendLine("== CAST");
        foreach (var npc in NpcAgent.All)
        {
            var b = Bounds(npc.gameObject);
            sb.AppendLine($"{npc.slug} pos={npc.transform.position:F2} scale={npc.transform.localScale.x:F2} " +
                          $"height={b.size.y:F2} stance='{npc.stance}'");
            foreach (var smr in npc.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                sb.AppendLine($"  SMR {smr.name} mesh={(smr.sharedMesh ? smr.sharedMesh.name : "NULL")} " +
                              $"verts={(smr.sharedMesh ? smr.sharedMesh.vertexCount : 0)} " +
                              $"tris={(smr.sharedMesh ? smr.sharedMesh.triangles.Length / 3 : 0)} " +
                              $"bones={smr.bones.Length} visible={smr.isVisible} " +
                              $"boundsY={smr.bounds.size.y:F2} mats=[{string.Join(",", smr.sharedMaterials.Select(m => m ? m.name : "null"))}]");
            var anim = npc.GetComponent<Animator>();
            if (anim != null)
                sb.AppendLine($"  ANIM human={anim.isHuman} ctrl={(anim.runtimeAnimatorController ? anim.runtimeAnimatorController.name : "NULL")} " +
                              $"state={(anim.GetCurrentAnimatorClipInfo(0).Length > 0 ? anim.GetCurrentAnimatorClipInfo(0)[0].clip.name : "?")}");
        }
        sb.AppendLine("== ARCHITECTURE (name pos boundsSize)");
        var inn = GameObject.Find("Inn");
        if (inn != null)
            foreach (Transform t in inn.transform)
                if (t.name.Contains("(Clone)") || t.name == "windowpane")
                {
                    var b = Bounds(t.gameObject);
                    sb.AppendLine($"{t.name} c={b.center:F1} s={b.size:F1}");
                }
        return sb.ToString();
    }

    static Bounds Bounds(GameObject go)
    {
        var b = new Bounds(go.transform.position, Vector3.zero); bool first = true;
        foreach (var r in go.GetComponentsInChildren<Renderer>())
        { if (first) { b = r.bounds; first = false; } else b.Encapsulate(r.bounds); }
        return b;
    }
}
