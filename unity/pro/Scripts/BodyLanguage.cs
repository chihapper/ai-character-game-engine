// Procedural life on top of the animation clips — the things the library can't give us
// because the rig has no facial bones: voice-driven head motion while a line actually PLAYS
// (people bob when they talk), leaning IN toward whoever they're talking to, and a laugh
// burst when the written line laughs. All applied post-Animator so poses survive.
using UnityEngine;

[DefaultExecutionOrder(200)]   // after NpcAgent's LateUpdate head-aim
public class BodyLanguage : MonoBehaviour
{
    Animator anim;
    NpcAgent npc;
    AudioSource voice;
    Transform head, chest;
    float[] envelope;          // per-50ms loudness of the current line (set by VoiceClient)
    float chuckle;             // >0 while a laugh burst plays out

    public void SetEnvelope(float[] env, AudioSource src) { envelope = env; voice = src; }
    public void Chuckle() { chuckle = 1.2f; }

    void Start()
    {
        anim = GetComponent<Animator>();
        npc = GetComponent<NpcAgent>();
        if (anim != null && anim.isHuman)
        {
            head = anim.GetBoneTransform(HumanBodyBones.Head);
            chest = anim.GetBoneTransform(HumanBodyBones.Chest)
                    ?? anim.GetBoneTransform(HumanBodyBones.Spine);
        }
    }

    void LateUpdate()
    {
        if (head == null) return;

        // lean IN toward the person being spoken to — engagement you can read across the room
        if (chest != null && npc != null && npc.LookTarget != null && anim.GetBool("Talk"))
        {
            var toward = npc.LookTarget.position - chest.position; toward.y = 0;
            if (toward.sqrMagnitude > 0.05f)
            {
                var axis = Vector3.Cross(Vector3.up, toward.normalized);
                chest.rotation = Quaternion.AngleAxis(7f, axis) * chest.rotation;
            }
        }

        // the voice moves the head: sample the line's loudness envelope at the playhead
        if (voice != null && voice.isPlaying && envelope != null && envelope.Length > 0 && voice.clip != null)
        {
            int i = Mathf.Clamp((int)(voice.time / 0.05f), 0, envelope.Length - 1);
            float amp = envelope[i];
            head.rotation = Quaternion.AngleAxis(amp * 9f, head.right) * head.rotation;
        }

        // laugh: quick head-back pulses, shoulders riding along through the chest bone
        if (chuckle > 0f)
        {
            chuckle -= Time.deltaTime;
            float pulse = Mathf.Abs(Mathf.Sin(chuckle * 14f)) * Mathf.Clamp01(chuckle);
            head.rotation = Quaternion.AngleAxis(-13f * pulse, head.right) * head.rotation;
            if (chest != null)
                chest.rotation = Quaternion.AngleAxis(-5f * pulse, chest.right) * chest.rotation;
        }
    }
}
