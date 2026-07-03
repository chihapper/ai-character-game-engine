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
        fill.type = LightType.Point; fill.range = 8f; fill.intensity = 1.2f;   // must not reach past the walls
        fill.color = new Color(1f, 0.96f, 0.9f);

        // first STATIC obstruction along a sight line — characters don't block camera spots
        // (clamping on a capsule parked the camera inside Bri's coat)
        float ClearDist(Vector3 from, Vector3 dir, float dist)
        {
            foreach (var h in Physics.RaycastAll(from, dir.normalized, dist)
                                     .OrderBy(h => h.distance))
            {
                if (h.collider.GetComponentInParent<NpcAgent>() != null) continue;
                if (h.collider.GetComponentInParent<PlayerController>() != null) continue;
                return h.distance;
            }
            return dist;
        }

        IEnumerator Shot(string name, Vector3 pos, Vector3 lookAt)
        {
            // an NPC facing a wall puts "2m in front of them" INSIDE the wall — pull the
            // camera back along the sight line, but never so close the subject gets near-plane
            // culled (that vanished Della from her own portrait)
            var dir = pos - lookAt;
            float d = ClearDist(lookAt, dir, dir.magnitude + 0.2f);
            if (d < dir.magnitude)
                pos = lookAt + dir.normalized * Mathf.Max(1.0f, d - 0.35f);
            cam.transform.position = pos;
            cam.transform.rotation = Quaternion.LookRotation(lookAt - pos);
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(Path.Combine(Dir, name + ".png"));
            yield return new WaitForSeconds(0.35f);   // let the async write land
        }

        foreach (var npc in NpcAgent.All.ToArray())
        {
            // portrait spot: in front if the room allows, else swing around until clear
            var head = npc.transform.position + Vector3.up * 1.45f;
            Vector3 spot = head + npc.transform.forward * 2.0f + Vector3.up * 0.1f;
            foreach (var yaw in new[] { 0f, 45f, -45f, 90f, -90f, 180f })
            {
                var dir = Quaternion.Euler(0, yaw, 0) * npc.transform.forward;
                float d = ClearDist(head, dir, 2.1f);
                if (d < 1.4f) continue;
                var cand = head + dir * Mathf.Min(2.0f, d - 0.35f) + Vector3.up * 0.1f;
                // another NPC standing on the sight line photobombs the portrait — Della's
                // close-up kept showing Edwin's face
                bool blocked = NpcAgent.All.Any(o => o != npc &&
                    DistToSegment(o.transform.position + Vector3.up * 1.3f, head, cand) < 0.55f);
                if (!blocked) { spot = cand; break; }
            }
            yield return Shot("npc_" + npc.slug.Split('-')[0], spot, head);
        }
        var hearth = Regions.Anchor("the hearth");
        var bar = Regions.Anchor("the bar");
        var door = Regions.Anchor("the door");
        var mid = Regions.Anchor("the middle of the taproom");
        yield return Shot("hearth", hearth + new Vector3(2.6f, 1.6f, 0.6f), hearth + Vector3.up * 0.8f);
        yield return Shot("bar", bar + new Vector3(-2.6f, 1.6f, -0.6f), bar + Vector3.up * 1.0f);
        yield return Shot("door_inside", mid + Vector3.up * 1.6f, door + Vector3.up * 1.2f);
        yield return Shot("room_wide", door + new Vector3(0, 1.8f, 0.6f), mid + Vector3.up * 1.5f);
        yield return Shot("window_inside", mid + new Vector3(0, 1.6f, -1f), mid + new Vector3(1.5f, 1.7f, 4f));
        yield return Shot("exterior_north", new Vector3(0, 2.2f, 12f), new Vector3(0, 1.5f, 4f));
        yield return Shot("exterior_door", door + new Vector3(0.5f, 1.7f, -5f), door + Vector3.up * 1.4f);

        // PLAYER-POV WALKTHROUGH — the shots above are MY canonical angles; these are the
        // player's actual eyes: their camera, their height, nameplates and UI included.
        // Door → room → bar (Della) → small table (Edwin) → long table (Bri) → hearth (Corvin) → kitchen.
        if (pc != null)
        {
            var ccc = pc.GetComponent<CharacterController>();
            if (ccc != null) ccc.enabled = false;      // scripted moves, not physics
            cam.transform.SetParent(pc.transform, false);
            cam.transform.localPosition = new Vector3(0, 1.6f, 0);
            cam.transform.localRotation = Quaternion.identity;

            IEnumerator Walk(Vector3 to)
            {
                to.y = 0;
                float guard = Time.time + 12f;
                while (Vector3.Distance(pc.transform.position, to) > 0.35f && Time.time < guard)
                {
                    var dir = to - pc.transform.position; dir.y = 0;
                    pc.transform.position += dir.normalized * 2.2f * Time.deltaTime;
                    pc.transform.rotation = Quaternion.Slerp(pc.transform.rotation,
                        Quaternion.LookRotation(dir), 8f * Time.deltaTime);
                    yield return null;
                }
            }
            IEnumerator Pov(string name, Vector3 lookAt)
            {
                var flat = lookAt - pc.transform.position; flat.y = 0;
                if (flat.sqrMagnitude > 0.01f) pc.transform.rotation = Quaternion.LookRotation(flat);
                cam.transform.localEulerAngles = new Vector3(
                    -Mathf.Rad2Deg * Mathf.Atan2(lookAt.y - 1.6f, Mathf.Max(0.1f, flat.magnitude)), 0, 0);
                yield return new WaitForSeconds(0.5f);
                yield return new WaitForEndOfFrame();
                ScreenCapture.CaptureScreenshot(Path.Combine(Dir, name + ".png"));
                yield return new WaitForSeconds(0.35f);
            }
            Vector3 NpcHead(string slugPrefix)
            {
                var n = NpcAgent.All.FirstOrDefault(a => a.slug.StartsWith(slugPrefix));
                return n != null ? n.transform.position + Vector3.up * 1.4f : mid + Vector3.up * 1.3f;
            }

            pc.transform.position = door + new Vector3(0, 0, 0.8f);
            yield return Pov("pov_1_from_door", mid + Vector3.up * 1.3f);
            yield return Walk(mid + new Vector3(0.4f, 0, 0));
            yield return Pov("pov_2_toward_bar", bar + Vector3.up * 1.1f);
            yield return Walk(bar + new Vector3(-0.7f, 0, 0.2f));
            yield return Pov("pov_3_della_at_bar", NpcHead("della"));
            yield return Pov("pov_4_edwin_small_table", NpcHead("edwin"));
            yield return Walk(Regions.Anchor("the long table") + new Vector3(1.3f, 0, 1.2f));
            yield return Pov("pov_5_bri_long_table", NpcHead("brielle"));
            yield return Walk(hearth + new Vector3(1.5f, 0, 0.9f));
            yield return Pov("pov_6_corvin_hearth", NpcHead("corvin"));
            yield return Walk(new Vector3(3.0f, 0, 0.8f));
            yield return Walk(new Vector3(4.2f, 0, -0.9f));
            yield return Pov("pov_7_back_kitchen", new Vector3(5.3f, 0.9f, -2.2f));
        }

        // SEAT INSPECTION: orbit every seated body up close — clipping, floating, and
        // sitting-on-the-table hide from canonical angles; they can't hide from an orbit
        foreach (var npc in NpcAgent.All.ToArray())
        {
            var a2 = npc.GetComponent<Animator>();
            if (a2 == null || !a2.GetBool("Sit")) continue;
            var c = npc.transform.position + Vector3.up * 0.8f;
            var nm = npc.slug.Split('-')[0];
            for (int k = 0; k < 4; k++)
            {
                var dir = Quaternion.Euler(0, 90f * k + 30f, 0) * Vector3.forward;
                float d2 = ClearDist(c, dir, 2.0f);
                yield return Shot($"seat_{nm}_{k}", c + dir * Mathf.Max(1.1f, d2 - 0.3f) + Vector3.up * 0.4f, c);
            }
        }

        // GESTURE PROOF: force-fire every wired one-shot on a standing NPC and photograph it
        // mid-clip. A trigger that doesn't change the picture is a broken wire — caught here,
        // not in the user's playtest.
        var subject = NpcAgent.All.FirstOrDefault(n =>
        { var an = n.GetComponent<Animator>(); return an != null && !an.GetBool("Sit"); })
            ?? NpcAgent.All.FirstOrDefault();
        if (subject != null)
        {
            var an2 = subject.GetComponent<Animator>();
            var head2 = subject.transform.position + Vector3.up * 1.2f;
            var gdir = subject.transform.forward;
            float gd = ClearDist(head2, gdir, 2.4f);
            var gpos = head2 + gdir * Mathf.Max(1.2f, gd - 0.35f) + Vector3.up * 0.25f;
            foreach (var trig in new[] { "Sip", "Nod", "Shrug", "Wave", "Startle", "Laugh", "Yawn", "Stretch", "Point" })
            {
                an2.SetTrigger(trig);
                yield return new WaitForSeconds(0.9f);
                yield return Shot("gesture_" + trig.ToLower(), gpos, head2);
                yield return new WaitForSeconds(1.8f);   // let the clip finish and the pose return
            }
        }

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

    static float DistToSegment(Vector3 p, Vector3 a, Vector3 b)
    {
        var ab = b - a;
        float t = Mathf.Clamp01(Vector3.Dot(p - a, ab) / Mathf.Max(1e-5f, ab.sqrMagnitude));
        return Vector3.Distance(p, a + ab * t);
    }

    static Bounds Bounds(GameObject go)
    {
        var b = new Bounds(go.transform.position, Vector3.zero); bool first = true;
        foreach (var r in go.GetComponentsInChildren<Renderer>())
        { if (first) { b = r.bounds; first = false; } else b.Encapsulate(r.bounds); }
        return b;
    }
}
