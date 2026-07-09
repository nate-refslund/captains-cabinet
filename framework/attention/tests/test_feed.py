"""TDD for framework.attention.feed — the P3 feed journal + cursor reads.

Every test points CABINET_FEED_DIR at a tmp dir (NEVER the real feed) and
drives the exact public API the channel agent codes against (§4.3). Writes
must be heard (append raises on failure); reads must be total on garbage.
"""
import json
import threading

import pytest

from framework.attention import feed


@pytest.fixture
def feed_dir(tmp_path, monkeypatch):
    d = tmp_path / "feed"
    monkeypatch.setenv("CABINET_FEED_DIR", str(d))
    return d


# --- append_event: stamping + pass-through ---------------------------------

def test_append_stamps_seq_and_ts_and_passes_extra_keys(feed_dir):
    row = feed.append_event({"direction": "out", "kind": "card",
                             "situation_key": "sk1", "class": "commit",
                             "gate_trace": ["floor:ok"], "telegram_message_id": 42})
    assert row["seq"] == 1
    assert row["ts"].endswith("Z")
    # every extra key survives untouched
    assert row["situation_key"] == "sk1"
    assert row["class"] == "commit"
    assert row["gate_trace"] == ["floor:ok"]
    assert row["telegram_message_id"] == 42
    # and it is persisted to exactly one UTC-day file
    files = list(feed_dir.glob("feed-*.jsonl"))
    assert len(files) == 1
    persisted = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert persisted["seq"] == 1
    assert persisted["situation_key"] == "sk1"


def test_append_respects_caller_preset_ts(feed_dir):
    row = feed.append_event({"direction": "in", "kind": "reply",
                             "ts": "2020-01-01T00:00:00Z"})
    assert row["ts"] == "2020-01-01T00:00:00Z"


def test_append_seq_monotonic_same_process(feed_dir):
    seqs = [feed.append_event({"direction": "out", "kind": "card"})["seq"]
            for _ in range(5)]
    assert seqs == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("bad", [
    {"kind": "card"},                        # missing direction
    {"direction": "sideways", "kind": "x"},  # unknown direction
    {"direction": "OUT", "kind": "x"},       # case-strict
    {"direction": "out"},                    # missing kind
    {"direction": "out", "kind": 7},         # non-str kind
    {"direction": "out", "kind": ""},        # empty kind carries no routing
    ["not", "a", "dict"],                    # not a dict at all
])
def test_append_validates_shape(feed_dir, bad):
    with pytest.raises(ValueError):
        feed.append_event(bad)


def test_append_failure_raises_when_dir_unwritable(tmp_path, monkeypatch):
    # CABINET_FEED_DIR points at an existing regular FILE, so mkdir fails — a
    # transport that cannot journal must be HEARD, not silent (§4.10 floor 2).
    blocker = tmp_path / "feed"
    blocker.write_text("i am a file, not a dir", encoding="utf-8")
    monkeypatch.setenv("CABINET_FEED_DIR", str(blocker))
    with pytest.raises(OSError):
        feed.append_event({"direction": "out", "kind": "card"})


# --- seq monotonicity across concurrent writers / lost high-water ----------

def test_seq_monotonic_across_threads(feed_dir):
    """Concurrent writers acquire the seq.txt flock separately — every returned
    seq must be unique and the whole set exactly 1..N (proves the on-disk
    high-water under lock, with no in-memory cache to skip)."""
    n_threads, per = 8, 12
    collected: list[int] = []
    guard = threading.Lock()

    def worker():
        local = [feed.append_event({"direction": "out", "kind": "card"})["seq"]
                 for _ in range(per)]
        with guard:
            collected.extend(local)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(collected)) == len(collected)            # no duplicate seq
    assert sorted(collected) == list(range(1, n_threads * per + 1))


def test_seq_recovers_from_feed_files_when_high_water_lost(feed_dir):
    """A corrupt or deleted seq.txt must NEVER re-issue a live seq — the
    high-water is re-derived from the durable feed files."""
    for _ in range(3):
        feed.append_event({"direction": "out", "kind": "card"})   # 1, 2, 3
    seq_txt = feed_dir / "seq.txt"
    seq_txt.write_text("garbage", encoding="utf-8")
    assert feed.append_event({"direction": "out", "kind": "card"})["seq"] == 4
    seq_txt.unlink()                                              # gone entirely
    assert feed.append_event({"direction": "out", "kind": "card"})["seq"] == 5


# --- feed_since: cursor semantics ------------------------------------------

def test_feed_since_returns_all_then_empty_at_boundary(feed_dir):
    for _ in range(3):
        feed.append_event({"direction": "out", "kind": "card"})
    rows, cur = feed.feed_since(0)
    assert [r["seq"] for r in rows] == [1, 2, 3]
    assert cur == 3
    # cursor at the last seq -> nothing new, SAME cursor (never re-read)
    rows2, cur2 = feed.feed_since(cur)
    assert rows2 == []
    assert cur2 == 3


def test_feed_since_max_n_cap_advances_only_to_last_returned(feed_dir):
    for _ in range(5):
        feed.append_event({"direction": "out", "kind": "card"})
    rows, cur = feed.feed_since(0, max_n=2)
    assert [r["seq"] for r in rows] == [1, 2]
    assert cur == 2                       # NOT 5 — cursor tracks returned rows
    rows2, cur2 = feed.feed_since(cur, max_n=2)
    assert [r["seq"] for r in rows2] == [3, 4]
    assert cur2 == 4
    rows3, cur3 = feed.feed_since(cur2, max_n=2)
    assert [r["seq"] for r in rows3] == [5]
    assert cur3 == 5


def test_feed_since_orders_by_seq_across_files(feed_dir):
    feed_dir.mkdir(parents=True, exist_ok=True)
    (feed_dir / "feed-2026-07-08.jsonl").write_text(
        json.dumps({"seq": 2, "direction": "out", "kind": "card"}) + "\n"
        + json.dumps({"seq": 4, "direction": "out", "kind": "card"}) + "\n",
        encoding="utf-8")
    (feed_dir / "feed-2026-07-09.jsonl").write_text(
        json.dumps({"seq": 1, "direction": "out", "kind": "card"}) + "\n"
        + json.dumps({"seq": 3, "direction": "out", "kind": "card"}) + "\n",
        encoding="utf-8")
    rows, cur = feed.feed_since(0)
    assert [r["seq"] for r in rows] == [1, 2, 3, 4]   # seq order, not file order
    assert cur == 4


def test_feed_since_missing_dir_returns_input_cursor(feed_dir):
    rows, cur = feed.feed_since(7)
    assert rows == []
    assert cur == 7


# --- recent_feed: bounded tail (re-anchoring only) -------------------------

def test_recent_feed_tail(feed_dir):
    for _ in range(5):
        feed.append_event({"direction": "out", "kind": "card"})
    assert [r["seq"] for r in feed.recent_feed(2)] == [4, 5]
    assert feed.recent_feed(0) == []
    assert [r["seq"] for r in feed.recent_feed(50)] == [1, 2, 3, 4, 5]


def test_recent_feed_missing_dir(feed_dir):
    assert feed.recent_feed(10) == []


# --- totality on garbage / unreadable --------------------------------------

def test_garbage_lines_and_rows_skipped(feed_dir):
    feed.append_event({"direction": "out", "kind": "card"})   # seq 1
    f = next(iter(feed_dir.glob("feed-*.jsonl")))
    with open(f, "a", encoding="utf-8") as fh:
        fh.write("not json at all\n")
        fh.write("\n")                                        # blank line
        fh.write(json.dumps(["a", "list", "not", "a", "dict"]) + "\n")
        fh.write(json.dumps({"seq": "notint", "direction": "out",
                             "kind": "x"}) + "\n")            # non-int seq
        fh.write(json.dumps({"seq": 2, "direction": "out", "kind": "edit"}) + "\n")
    rows, cur = feed.feed_since(0)
    assert [r["seq"] for r in rows] == [1, 2]
    assert cur == 2


def test_unreadable_file_skipped_not_raised(feed_dir):
    feed.append_event({"direction": "out", "kind": "card"})   # seq 1
    bad = feed_dir / "feed-2000-01-01.jsonl"
    bad.write_text('{"seq": 99, "direction": "out", "kind": "card"}\n',
                   encoding="utf-8")
    bad.chmod(0o000)
    try:
        rows, _ = feed.feed_since(0)
        seqs = [r["seq"] for r in rows]
        assert 1 in seqs and 99 not in seqs   # skipped silently, read stays total
    finally:
        bad.chmod(0o644)


# --- consumer cursors: roundtrip, corruption, traversal fence --------------

def test_cursor_roundtrip_and_corrupt_reads_zero(feed_dir):
    assert feed.load_cursor("t2-dossier") == 0        # absent -> 0
    feed.store_cursor("t2-dossier", 17)
    assert feed.load_cursor("t2-dossier") == 17       # roundtrip
    (feed_dir / "cursors" / "t2-dossier.txt").write_text("not-a-number",
                                                         encoding="utf-8")
    assert feed.load_cursor("t2-dossier") == 0        # corrupt -> 0


def test_cursor_valid_ids_accepted(feed_dir):
    for cid in ("comms_retro", "gate-dedup", "briefing3", "a"):
        feed.store_cursor(cid, 5)
        assert feed.load_cursor(cid) == 5


@pytest.mark.parametrize("bad_id",
                         ["../x", "a/b", "x/../y", "AbC", "with space",
                          "", "dot.dot", "tab\tid", "..", "/abs"])
def test_consumer_id_traversal_rejected(feed_dir, bad_id):
    with pytest.raises(ValueError):
        feed.load_cursor(bad_id)
    with pytest.raises(ValueError):
        feed.store_cursor(bad_id, 1)
