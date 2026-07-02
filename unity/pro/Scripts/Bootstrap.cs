// FerryCrossingPro bootstrap — an empty URP scene plus these scripts is the whole game.
// Real inn (MegaKit), real bodies (UBC + UAL), URP mood lighting + post, and the same mind
// server driving the same unchanged engine.
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

public class Bootstrap : MonoBehaviour
{
    public static string PlayerHandle = "the stranger just in from the storm";
    public static Light Sun;                                  // StormAudio flickers it for lightning
    public static List<Material> WindowPanes => InnBuilder.WindowPanes;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void SelfSpawn() => new GameObject("Bootstrap").AddComponent<Bootstrap>();

    IEnumerator Start()
    {
        foreach (var cam in FindObjectsByType<Camera>(FindObjectsSortMode.None))
            cam.gameObject.SetActive(false);
        foreach (var al in FindObjectsByType<AudioListener>(FindObjectsSortMode.None))
            al.enabled = false;

        Mood();
        var baked = FindFirstObjectByType<WorldMarker>();
        if (baked != null)
            baked.Restore();       // the world was built (and possibly hand-adjusted) in the editor
        else
        {
            InnBuilder.Build();
            ExteriorBuilder.Build();   // the storm is a place now, not just a sound
        }
        Fires();
        BakeNav();                 // paths that go AROUND the furniture
        gameObject.AddComponent<StormAudio>();
        gameObject.AddComponent<StoryDirector>();
        var mind = gameObject.AddComponent<MindClient>();
        gameObject.AddComponent<DialogueUI>();
        gameObject.AddComponent<CurtainUI>();   // title in, epilogue out
        gameObject.AddComponent<VoiceClient>(); // their voices out, your voice in
        gameObject.AddComponent<AutoShot>();    // self-photographing test rig (inert without flag)

        // the player: a body-less first-person presence (CharacterController is the LoS collider)
        var player = new GameObject("Player");
        player.transform.position = Regions.Anchor("the door") + new Vector3(0, 0.02f, 0.4f);
        player.AddComponent<PlayerController>();

        yield return mind.CreateSession(s =>
        {
            PlayerHandle = string.IsNullOrEmpty(s.player_handle) ? PlayerHandle : s.player_handle;
            VoiceClient.ServerHasVoice = s.voice;
            SpawnCast(s);
            DialogueUI.I.Feed("—", $"{s.title} · the storm closes in. Find the bar.");
        });
    }

    void Mood()
    {
        // cold, wet, dim — the fires are the only warmth (same design as the gray box, real now)
        RenderSettings.skybox = null;   // the DEFAULT skybox is a sunny day — this night is lit by fire
        // a null skybox still CLEARS to a bright day-gray gradient — through every window the
        // "night" read as noon. Clear to storm-black instead.
        if (Camera.main != null)
        {
            Camera.main.clearFlags = CameraClearFlags.SolidColor;
            Camera.main.backgroundColor = new Color(0.015f, 0.02f, 0.035f);
        }
        // no skybox → glossy surfaces mirror the DEFAULT pale-gray environment: the flooded
        // crossing rendered as a glowing band across every north window. Kill env reflections.
        RenderSettings.reflectionIntensity = 0.12f;
        RenderSettings.ambientMode = AmbientMode.Flat;
        RenderSettings.ambientLight = new Color(0.11f, 0.12f, 0.16f);
        RenderSettings.fog = true;
        RenderSettings.fogMode = FogMode.Exponential;
        // fog must fade to NIGHT, not day-gray — a light fogColor painted a glowing horizon
        // band across every window and washed the marsh silhouettes pale
        RenderSettings.fogColor = new Color(0.025f, 0.03f, 0.045f);
        RenderSettings.fogDensity = 0.045f;

        Sun = new GameObject("StormLight").AddComponent<Light>();
        Sun.type = LightType.Directional;
        Sun.intensity = 0.14f;
        Sun.color = new Color(0.55f, 0.63f, 0.8f);
        Sun.transform.rotation = Quaternion.Euler(55, -28, 0);
        Sun.shadows = LightShadows.Soft;

        // global post volume, created in code: gentle bloom for the flames, cool grade, vignette
        var vgo = new GameObject("PostVolume");
        var vol = vgo.AddComponent<Volume>();
        vol.isGlobal = true;
        var profile = ScriptableObject.CreateInstance<VolumeProfile>();
        var bloom = profile.Add<Bloom>();
        bloom.intensity.Override(0.9f);
        bloom.threshold.Override(1.05f);
        var grade = profile.Add<ColorAdjustments>();
        grade.postExposure.Override(0.15f);
        grade.contrast.Override(12f);
        grade.colorFilter.Override(new Color(0.92f, 0.95f, 1.05f));
        grade.saturation.Override(-8f);
        var vig = profile.Add<Vignette>();
        vig.intensity.Override(0.28f);
        vig.smoothness.Override(0.45f);
        vol.profile = profile;
    }

    void BakeNav()
    {
        var go = new GameObject("NavMesh");
        var surf = go.AddComponent<Unity.AI.Navigation.NavMeshSurface>();
        surf.useGeometry = UnityEngine.AI.NavMeshCollectGeometry.PhysicsColliders;
        surf.BuildNavMesh();
    }

    void Fires()
    {
        var hearthFire = Regions.Anchor("the hearth") + new Vector3(-0.7f, 0.55f, 0);
        Fire("hearthfire", hearthFire, new Color(1f, 0.52f, 0.22f), 2.4f, 0.6f, 9f, 2.4f);
        FlameFX.Add(hearthFire + Vector3.down * 0.35f, 1.6f);                                  // the fire itself
        FlameFX.Add(Regions.Anchor("the bar") + new Vector3(1.0f, 1.06f, -0.4f), 0.3f);        // bar candle
        FlameFX.Add(Regions.Anchor("the long table") + new Vector3(-0.8f, 1.0f, -0.8f), 0.3f); // table candle
        Fire("chandelier", new Vector3(0, InnBuilder.WallHeight - 0.6f, 0),
             new Color(1f, 0.72f, 0.42f), 1.3f, 0.15f, 8f, 1.0f);
        Fire("candle.bar", Regions.Anchor("the bar") + new Vector3(1.0f, 1.25f, -0.4f),
             new Color(1f, 0.7f, 0.4f), 0.8f, 0.15f, 4.5f, 1.4f);
        Fire("candle.table", Regions.Anchor("the long table") + new Vector3(-0.8f, 1.2f, -0.8f),
             new Color(1f, 0.68f, 0.38f), 0.7f, 0.12f, 4f, 1.4f);
        Fire("lantern.door", Regions.Anchor("the door") + new Vector3(0.9f, 1.95f, -0.5f),
             new Color(1f, 0.75f, 0.45f), 0.8f, 0.1f, 5f, 0.9f);
    }

    static void Fire(string name, Vector3 pos, Color c, float intensity, float flicker, float range, float speed)
    {
        var go = new GameObject(name);
        go.transform.position = pos;
        var lt = go.AddComponent<Light>();
        lt.type = LightType.Point; lt.color = c; lt.range = range;
        lt.shadows = name == "hearthfire" ? LightShadows.Soft : LightShadows.None;
        var f = go.AddComponent<Flicker>();
        f.baseIntensity = intensity; f.amount = flicker; f.speed = speed;
    }

    /// The opening tableau the player walks into: bodies already SITTING and LEANING, not four
    /// mannequins standing at attention. Their minds take over from here.
    static void OpeningPose(string slug, GameObject body)
    {
        var anim = body.GetComponent<Animator>();
        if (anim == null) return;
        if (slug.StartsWith("edwin") || slug.StartsWith("brielle"))
        {
            var seat = InnBuilder.Seats.OrderBy(sp => (sp.pos - body.transform.position).sqrMagnitude).First();
            body.transform.position = seat.pos + Vector3.up * 0.05f;
            var face = seat.face - body.transform.position; face.y = 0;
            if (face.sqrMagnitude > 0.01f) body.transform.rotation = Quaternion.LookRotation(face);
            anim.SetBool("Sit", true);
        }
        else if (slug.StartsWith("corvin"))
        {
            // shoulder against the west wall beside the hearth, angled to watch the door
            body.transform.position = new Vector3(-5.35f, 0, -1.35f);
            body.transform.rotation = Quaternion.LookRotation(new Vector3(0.85f, 0, -0.5f));
            anim.SetBool("Lean", true);
        }
    }

    void SpawnCast(SessionRes s)
    {
        var looks = new Dictionary<string, (string region, string stance, CastLook look)>
        {
            { "della-fenwick", ("the bar", "working the bar, wiping glasses", new CastLook {
                feminine = true, height = 0.98f, darkSkin = false, hair = "Hair_Buns",
                hairColor = new Color(0.32f, 0.2f, 0.11f), outfit = "Female_Peasant",
                outfitTint = new Color(0.75f, 0.7f, 0.62f, 1f),
                top = new Color(0.55f, 0.48f, 0.4f), bottom = new Color(0.35f, 0.28f, 0.22f) }) },
            { "corvin-ashgrave-inworld", ("the hearth", "leaning on the wall by the fire, nursing a cup, eyes on the door", new CastLook {
                feminine = false, height = 1.04f, darkSkin = true, hair = "Hair_Buzzed", beard = true,
                hairColor = new Color(0.09f, 0.09f, 0.1f), outfit = "Male_Ranger",
                outfitTint = new Color(0.35f, 0.38f, 0.42f, 1f),   // hooded, storm-dark
                top = new Color(0.2f, 0.22f, 0.26f), bottom = new Color(0.14f, 0.15f, 0.18f) }) },
            { "edwin-hale", ("a small table", "sitting at the small table across the bar, drying out, watching the room", new CastLook {
                feminine = false, height = 0.99f, darkSkin = false, hair = "Hair_SimpleParted",
                hairColor = new Color(0.72f, 0.45f, 0.2f), outfit = "Male_Peasant",
                outfitTint = new Color(0.85f, 0.5f, 0.75f, 1f),   // the performer wears it LOUD
                top = new Color(0.6f, 0.28f, 0.5f), bottom = new Color(0.25f, 0.32f, 0.5f) }) },
            { "brielle-bri-castellano", ("the long table", "at the long table mid-room, cloak shed, sitting straight, taking in the room", new CastLook {
                feminine = true, height = 0.93f, darkSkin = true, hair = "Hair_Long",
                hairColor = new Color(0.1f, 0.08f, 0.08f),
                outfitPieces = new[] { "Female_Ranger_Body", "Female_Ranger_Arms",
                                       "Female_Ranger_Legs", "Female_Ranger_Feet" },  // traveler, NO hood
                outfitTint = new Color(0.9f, 0.82f, 0.65f, 1f),
                top = new Color(0.85f, 0.75f, 0.58f), bottom = new Color(0.35f, 0.4f, 0.5f) }) },
        };
        foreach (var c in s.cast)
        {
            (string region, string stance, CastLook look) cfg = looks.TryGetValue(c.slug, out var v) ? v
                : ("the middle of the taproom", "", new CastLook { height = 1f, hair = "Hair_SimpleParted" });
            var body = CastBuilder.Build(c.handle, Regions.Anchor(cfg.region) + new Vector3(0.4f, 0, 0.2f), cfg.look);
            var agent = body.AddComponent<NpcAgent>();
            agent.slug = c.slug; agent.handle = c.handle; agent.stance = cfg.stance;
            body.AddComponent<Nameplate>().text = () => agent.Reference;
            OpeningPose(c.slug, body);
        }
    }
}
