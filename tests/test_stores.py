"""State integrity (memory/base_store.py + the five stores) — the arch-review theme-A guarantees:
shared truth across instances, atomic writes, frozen readonly, loud (quarantined) corruption.
Codifies the validation run when the NamespaceStore landed."""
import asyncio
import glob
import json
import os

from orchestrator.memory.agency_store import AgencyStore
from orchestrator.memory.commitments import CommitmentStore
from orchestrator.memory.intent import IntentStore
from orchestrator.memory.long_term import LongTermMemory
from orchestrator.memory.relationship import RelationshipStore


def test_two_instances_share_one_truth(mem_dir):
    a, b = LongTermMemory("share-ns"), LongTermMemory("share-ns")
    asyncio.run(a.remember("the harbor bridge burned", t=1.0))
    asyncio.run(b.remember("a stranger arrived", t=2.0))
    asyncio.run(b.remember("a stranger arrived", t=3.0))  # dedup -> reinforce -> whole-file rewrite from B
    lines = (mem_dir / "share-ns.jsonl").read_text(encoding="utf-8").strip().splitlines()
    texts = [json.loads(ln)["text"] for ln in lines]
    assert "the harbor bridge burned" in texts and len(texts) == 2  # B's rewrite kept A's record
    assert any(json.loads(ln).get("reinforcement") == 1 for ln in lines)
    assert not glob.glob(str(mem_dir / "*.tmp"))  # atomic replace left no litter


def test_invalidate_prevents_resurrection(mem_dir):
    a = LongTermMemory("wipe-ns")
    asyncio.run(a.remember("doomed memory", t=1.0))
    for f in glob.glob(str(mem_dir / "wipe-ns.*")):
        os.remove(f)
    LongTermMemory.invalidate("wipe-ns")
    assert LongTermMemory("wipe-ns")._all() == []


def test_readonly_is_frozen_everywhere():
    rs = RelationshipStore("ro-ns", readonly=True)
    before = rs.get().trust
    rs.update(d_trust=0.3)
    assert rs.get().trust == before

    ist = IntentStore("ro-ns", readonly=True)
    ist.update("new aim")
    assert ist.get().intent == ""

    ag = AgencyStore("ro-ns", readonly=True)
    ag.set_goals(["x"])
    ag.mark_deliberated(5.0)
    assert ag.goals() is None and ag.last_t() is None

    rw = CommitmentStore("ro-rw")
    cid = rw.add("meet at dawn", due_t=1.0).id
    ro = CommitmentStore("ro-rw", readonly=True)
    assert ro.sweep_expired(9.0) == []
    assert ro.resolve(cid, "fulfilled") is None
    assert all(c.status == "open" for c in ro._all())


def test_corrupt_json_store_is_quarantined_not_silently_reset(mem_dir):
    p = mem_dir / "corrupt-ns.relationship.json"
    p.write_text("{ NOT JSON", encoding="utf-8")
    st = RelationshipStore("corrupt-ns").get()
    assert st.trust == 0.5  # fresh default...
    assert glob.glob(str(p) + ".corrupt-*")  # ...but the evidence is preserved
    assert not p.exists()


def test_partial_jsonl_salvages_good_lines(mem_dir):
    p = mem_dir / "partial-ns.jsonl"
    good = json.dumps({"text": "good memory", "importance": 0.7, "kind": "world_event",
                       "when": "", "index": 0})
    p.write_text(good + "\n{truncated", encoding="utf-8")
    assert [r.text for r in LongTermMemory("partial-ns")._all()] == ["good memory"]
