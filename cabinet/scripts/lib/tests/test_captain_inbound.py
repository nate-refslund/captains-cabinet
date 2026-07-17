"""READ side of the durable captain-inbound archive (captain_inbound.py).

The write side (officer-inbound-poller.py::archive_captain_dm, pinned in
cabinet/scripts/tests/test_inbound_poller_inbound_archive.py) appends
verbatim JSONL rows to UTC day files and EXPLICITLY permits duplicate
dm_ids (crash-mid-deliver replay). These tests pin the reader half of that
contract: dedup-by-dm_id-last-occurrence-wins, newest-first orderings,
both ``get`` id forms + the ambiguity shape, all-terms lexical search,
garbage tolerance (the feed-loader discipline), the degrade-visible
semantic_search fallback, and the CLI smoke path.

Every test sets CABINET_CAPTAIN_INBOUND_DIR explicitly (the repo-root
conftest already fences it session-wide — this is the belt on top of that
suspender, and what the write-side suite does too). Ids are deliberately
FAKE (4242-style) and epoch fixtures stay ≤8 digits: this file ships in
the egg, and the publish gate flags any 9+-digit run as a possible real
chat id.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import captain_inbound

# Captured at import time, BEFORE any test runs: test_library_mcp_client
# patches the global subprocess.Popen and the patch can leak across
# modules in a shared pytest session — restore the real one around every
# spawn here (semantic_search and the CLI smoke tests both fork), the
# exact guard test_memory_search_sh.py uses.
_REAL_POPEN = subprocess.Popen

SCRIPTS_DIR = Path(__file__).resolve().parents[2]  # cabinet/scripts
CLI = SCRIPTS_DIR / "captain-inbound.py"


def _row(dm_id, message_id, text, *, kind="text", ts="", quoted="",
         file_kind="", file_name="", chat_id="", update_id=1):
    return {
        "v": 1, "dm_id": dm_id,
        "chat_id": chat_id or dm_id.split("-")[1],
        "message_id": message_id, "update_id": update_id, "officer": "cos",
        "kind": kind, "text": text, "quoted": quoted,
        "file_kind": file_kind, "file_name": file_name,
        "tg_date": 12345601, "ts": ts,
    }


def _write_archive(tmp_path, monkeypatch) -> Path:
    """Three day files + garbage, mirroring the writer's real shapes:
    a crash-replayed duplicate (same dm_id, later ts), a file row, an
    onboarding row, and a bare-mid collision across two chats."""
    d = tmp_path / "captain-inbound"
    d.mkdir()
    monkeypatch.setenv("CABINET_CAPTAIN_INBOUND_DIR", str(d))

    day1 = [
        json.dumps(_row("tg-4242-1", 1, "godmorgen skib — status?",
                        ts="2026-07-01T08:00:00Z"), ensure_ascii=False),
        json.dumps(_row("tg-4242-2", 2, "the spec", kind="file",
                        file_kind="document", file_name="egg-spec.pdf",
                        ts="2026-07-01T09:00:00Z"), ensure_ascii=False),
        "this line is not json",
        '"a json scalar, not a row"',
        json.dumps({"kind": "text", "text": "row without a dm_id"}),
        "",
    ]
    day2 = [
        json.dumps(_row("tg-4242-3", 3, "Ship the EGG til fredag",
                        quoted="the draft plan",
                        ts="2026-07-02T10:00:00Z"), ensure_ascii=False),
        # Crash-replay duplicate of tg-4242-1: verbatim content, later
        # append-time ts — the reader must keep THIS one and rank the dm
        # at THIS position.
        json.dumps(_row("tg-4242-1", 1, "godmorgen skib — status?",
                        ts="2026-07-02T10:05:00Z"), ensure_ascii=False),
    ]
    day3 = [
        json.dumps(_row("tg-4242-7", 7, "syv fra kaptajnens chat",
                        ts="2026-07-03T08:00:00Z"), ensure_ascii=False),
        json.dumps(_row("tg-777-7", 7, "syv fra gruppechatten",
                        ts="2026-07-03T09:00:00Z"), ensure_ascii=False),
        json.dumps(_row("tg-777-9", 9, "onboarding start",
                        kind="onboarding",
                        ts="2026-07-03T10:00:00Z"), ensure_ascii=False),
    ]
    (d / "inbound-2026-07-01.jsonl").write_text(
        "\n".join(day1) + "\n", encoding="utf-8")
    (d / "inbound-2026-07-02.jsonl").write_text(
        "\n".join(day2) + "\n", encoding="utf-8")
    (d / "inbound-2026-07-03.jsonl").write_text(
        "\n".join(day3) + "\n", encoding="utf-8")
    return d


# --- iter_rows -------------------------------------------------------------


def test_iter_rows_oldest_to_newest_skips_garbage(tmp_path, monkeypatch):
    _write_archive(tmp_path, monkeypatch)
    rows = list(captain_inbound.iter_rows())
    # Raw stream: replay duplicate present, garbage lines absent.
    assert [r["dm_id"] for r in rows] == [
        "tg-4242-1", "tg-4242-2", "tg-4242-3", "tg-4242-1",
        "tg-4242-7", "tg-777-7", "tg-777-9"]
    assert all(isinstance(r, dict) and r["dm_id"] for r in rows)


def test_iter_rows_days_window_and_missing_dir(tmp_path, monkeypatch):
    _write_archive(tmp_path, monkeypatch)
    assert [r["dm_id"] for r in captain_inbound.iter_rows(days=1)] == [
        "tg-4242-7", "tg-777-7", "tg-777-9"]
    assert list(captain_inbound.iter_rows(days=0)) == []
    monkeypatch.setenv("CABINET_CAPTAIN_INBOUND_DIR",
                       str(tmp_path / "nowhere"))
    assert list(captain_inbound.iter_rows()) == []


# --- latest ------------------------------------------------------------------


def test_latest_newest_first_dedup_last_wins(tmp_path, monkeypatch):
    _write_archive(tmp_path, monkeypatch)
    rows = captain_inbound.latest()
    # tg-4242-1 appears ONCE, ranked at its replay (day-2) position —
    # newer than tg-4242-3, older than the day-3 rows — and carries the
    # replay's later ts.
    assert [r["dm_id"] for r in rows] == [
        "tg-777-9", "tg-777-7", "tg-4242-7", "tg-4242-1",
        "tg-4242-3", "tg-4242-2"]
    assert rows[3]["ts"] == "2026-07-02T10:05:00Z"
    assert [r["dm_id"] for r in captain_inbound.latest(n=2)] == [
        "tg-777-9", "tg-777-7"]
    assert captain_inbound.latest(n=0) == []


def test_latest_kind_filter_shapes(tmp_path, monkeypatch):
    _write_archive(tmp_path, monkeypatch)
    assert [r["dm_id"] for r in captain_inbound.latest(kinds="file")] == [
        "tg-4242-2"]
    # Iterable and comma-list shapes are equivalent (the CLI feeds both).
    for kinds in (["onboarding", "file"], "onboarding,file"):
        assert [r["dm_id"] for r in captain_inbound.latest(kinds=kinds)] == [
            "tg-777-9", "tg-4242-2"]


# --- get ---------------------------------------------------------------------


def test_get_full_form_and_miss(tmp_path, monkeypatch):
    _write_archive(tmp_path, monkeypatch)
    row = captain_inbound.get("tg-4242-3")
    assert row is not None
    assert row["text"] == "Ship the EGG til fredag"
    assert "matches" not in row
    assert captain_inbound.get("tg-4242-4242") is None
    assert captain_inbound.get("junk") is None
    assert captain_inbound.get(None) is None


def test_get_bare_mid_unambiguous(tmp_path, monkeypatch):
    _write_archive(tmp_path, monkeypatch)
    for form in (3, "3"):
        row = captain_inbound.get(form)
        assert row["dm_id"] == "tg-4242-3"
        assert "matches" not in row  # single chat → plain row, no wrapper


def test_get_bare_mid_ambiguous_returns_newest_plus_matches(
        tmp_path, monkeypatch):
    _write_archive(tmp_path, monkeypatch)
    row = captain_inbound.get(7)
    assert row["dm_id"] == "tg-777-7"  # newest by archive order
    assert [m["dm_id"] for m in row["matches"]] == ["tg-777-7", "tg-4242-7"]
    assert all(m.get("text") for m in row["matches"])  # full rows, not stubs
    # The wrapper is a COPY — direct lookups stay unpolluted.
    assert "matches" not in captain_inbound.get("tg-777-7")


# --- search ------------------------------------------------------------------


def test_search_all_terms_case_insensitive_all_fields(tmp_path, monkeypatch):
    _write_archive(tmp_path, monkeypatch)
    # Terms hit across text (EGG, case-insensitive) and file_name
    # (egg-spec.pdf) — newest first.
    assert [r["dm_id"] for r in captain_inbound.search("egg")] == [
        "tg-4242-3", "tg-4242-2"]
    # ALL terms must match, together only satisfied by the day-2 text row.
    assert [r["dm_id"] for r in captain_inbound.search("EGG fredag")] == [
        "tg-4242-3"]
    # quoted field is searched too.
    assert [r["dm_id"] for r in captain_inbound.search("draft plan")] == [
        "tg-4242-3"]
    # Any unmatched term kills the row; empty query returns nothing.
    assert captain_inbound.search("egg mangler-helt") == []
    assert captain_inbound.search("") == []
    assert captain_inbound.search("   ") == []


def test_search_kind_filter_and_cap(tmp_path, monkeypatch):
    _write_archive(tmp_path, monkeypatch)
    assert [r["dm_id"] for r in captain_inbound.search("egg", kinds="file")
            ] == ["tg-4242-2"]
    assert [r["dm_id"] for r in captain_inbound.search("egg", n=1)] == [
        "tg-4242-3"]


# --- semantic_search ---------------------------------------------------------


def _with_real_popen(fn):
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        return fn()
    finally:
        subprocess.Popen = patched


def test_semantic_search_unavailable_never_raises(tmp_path, monkeypatch):
    _write_archive(tmp_path, monkeypatch)
    missing = tmp_path / "no-such-search-memory.sh"
    monkeypatch.setenv("CABINET_MEMORY_SEARCH_SH", str(missing))
    res = _with_real_popen(
        lambda: captain_inbound.semantic_search("egg fredag"))
    assert res["available"] is False
    assert str(missing) in res["reason"]
    assert res["results"] == []
    # Empty query degrades the same visible way.
    empty = _with_real_popen(lambda: captain_inbound.semantic_search("  "))
    assert empty["available"] is False and empty["results"] == []


def test_semantic_search_nonzero_exit_is_unavailable(tmp_path, monkeypatch):
    _write_archive(tmp_path, monkeypatch)
    stub = tmp_path / "stub-search.sh"
    stub.write_text("#!/bin/bash\necho boom >&2\nexit 3\n", encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("CABINET_MEMORY_SEARCH_SH", str(stub))
    res = _with_real_popen(lambda: captain_inbound.semantic_search("egg"))
    assert res["available"] is False
    assert "exited 3" in res["reason"] and "boom" in res["reason"]


def test_semantic_search_timeout_is_unavailable(tmp_path, monkeypatch):
    _write_archive(tmp_path, monkeypatch)
    stub = tmp_path / "stub-sleep.sh"
    # exec so the kill hits sleep itself (no orphan grandchild holding
    # the pipe open past the timeout).
    stub.write_text("#!/bin/bash\nexec sleep 5\n", encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("CABINET_MEMORY_SEARCH_SH", str(stub))
    res = _with_real_popen(
        lambda: captain_inbound.semantic_search("egg", timeout=0.2))
    assert res["available"] is False
    assert "timed out" in res["reason"]


def test_semantic_search_parses_and_joins_verbatim_rows(
        tmp_path, monkeypatch):
    """Pin the discovered search-memory.sh interface: argv shape in, the
    ``[trust:…] [type] ref by who @ when (sim: …, score: …)`` + indented
    preview shape out, and the ref→dm_id join that restores the verbatim
    archive row a 200-char flattened memory preview cannot."""
    _write_archive(tmp_path, monkeypatch)
    argv_out = tmp_path / "argv.txt"
    stub = tmp_path / "stub-search.sh"
    stub.write_text(
        "#!/bin/bash\n"
        "printf '%s\\n' \"$@\" > " + str(argv_out) + "\n"
        "cat <<'EOF'\n"
        "=== Cabinet Memory Search: 'egg til fredag' ===\n"
        "Type: telegram_dm\n"
        "\n"
        "[trust:derived] [telegram_dm] tg-4242-3 by cos @ 2026-07-02 10:00 "
        "(sim: 0.91, score: 0.78)\n"
        "  Ship the EGG til fredag\n"
        "\n"
        "[trust:asserted] [telegram_dm] tg-8888-5 by cos @ 2026-07-01 08:00 "
        "(sim: 0.55, score: 0.41)\n"
        "  a memory row with no archived twin\n"
        "\n"
        "EOF\n", encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("CABINET_MEMORY_SEARCH_SH", str(stub))

    res = _with_real_popen(
        lambda: captain_inbound.semantic_search("egg til fredag", n=5))
    assert res["available"] is True
    assert [h["ref"] for h in res["results"]] == ["tg-4242-3", "tg-8888-5"]

    joined = res["results"][0]
    assert joined["trust"] == "derived"
    assert joined["source_type"] == "telegram_dm"
    assert joined["similarity"] == "0.91" and joined["score"] == "0.78"
    assert joined["preview"] == "Ship the EGG til fredag"
    assert joined["dm_id"] == "tg-4242-3"
    assert joined["archive"]["text"] == "Ship the EGG til fredag"
    assert joined["archive"]["quoted"] == "the draft plan"  # verbatim row

    orphan = res["results"][1]
    assert orphan["dm_id"] == "tg-8888-5"
    assert orphan["archive"] is None  # memory row without an archive twin

    argv = argv_out.read_text(encoding="utf-8").splitlines()
    assert argv == ["--type", "telegram_dm", "--limit", "5",
                    "egg til fredag"]


def test_semantic_officer_reply_refs_never_labeled_captain(
        tmp_path, monkeypatch):
    """Review P1-1: the telegram_dm memory type ALSO carries officer
    OUTBOUND replies (post-reply-memory.sh, ref ``tg-out-<ts>-<officer>``)
    and id-less inbound fallbacks (``tg-in-<ts>-<officer>``). Those must
    NEVER be labeled with a dm_id — a reader of this tool would otherwise
    misattribute OFFICER speech as Captain speech, the exact failure the
    archive exists to kill. Negative group-chat ids still qualify."""
    _write_archive(tmp_path, monkeypatch)
    stub = tmp_path / "stub-officer.sh"
    stub.write_text(
        "#!/bin/bash\n"
        "cat <<'EOF'\n"
        "=== Cabinet Memory Search: 'plan' ===\n"
        "\n"
        "[trust:derived] [telegram_dm] tg-out-1700-cos by cos @ "
        "2026-07-02 10:00 (sim: 0.9, score: 0.8)\n"
        "  an OFFICER reply, not the Captain\n"
        "\n"
        "[trust:derived] [telegram_dm] tg-in-1700-cos by cos @ "
        "2026-07-02 10:01 (sim: 0.8, score: 0.7)\n"
        "  id-less inbound fallback row\n"
        "\n"
        "[trust:derived] [telegram_dm] tg--10042-7 by cos @ "
        "2026-07-02 10:02 (sim: 0.7, score: 0.6)\n"
        "  negative group-chat id IS a real dm_id shape\n"
        "\n"
        "EOF\n", encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("CABINET_MEMORY_SEARCH_SH", str(stub))
    res = _with_real_popen(
        lambda: captain_inbound.semantic_search("plan", n=5))
    assert res["available"] is True
    out_hit, in_hit, neg_hit = res["results"]
    assert out_hit["dm_id"] == "" and out_hit["archive"] is None
    assert in_hit["dm_id"] == "" and in_hit["archive"] is None
    assert neg_hit["dm_id"] == "tg--10042-7"


def test_semantic_no_results_is_available_true_empty(tmp_path, monkeypatch):
    """Review P2-5a: the entrypoint's explicit "No results found." (exit 0)
    is the honest-zero contract — available True, zero results, and the
    stderr tail surfaced (e.g. the embedding-degrade WARN)."""
    _write_archive(tmp_path, monkeypatch)
    stub = tmp_path / "stub-empty.sh"
    stub.write_text(
        "#!/bin/bash\n"
        "echo 'WARN: embedding degraded — lexical fallback' >&2\n"
        "echo 'No results found.'\n", encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("CABINET_MEMORY_SEARCH_SH", str(stub))
    res = _with_real_popen(
        lambda: captain_inbound.semantic_search("nothing matches", n=5))
    assert res["available"] is True
    assert res["results"] == []
    assert any("WARN" in ln for ln in res["stderr_tail"])


def test_semantic_format_drift_degrades_loudly(tmp_path, monkeypatch):
    """Review P2-3: the banner prints ONLY when hits exist — a banner with
    zero parsed hit lines and no "No results found." means the hit-line
    format drifted under our parser. That must be available=False, never a
    silent (false) empty result."""
    _write_archive(tmp_path, monkeypatch)
    stub = tmp_path / "stub-drift.sh"
    stub.write_text(
        "#!/bin/bash\n"
        "cat <<'EOF'\n"
        "=== Cabinet Memory Search: 'egg' ===\n"
        "\n"
        "trust=derived type=telegram_dm ref=tg-4242-3 REORDERED FORMAT\n"
        "EOF\n", encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("CABINET_MEMORY_SEARCH_SH", str(stub))
    res = _with_real_popen(
        lambda: captain_inbound.semantic_search("egg", n=5))
    assert res["available"] is False
    assert "format drift" in res["reason"]


# --- CLI smoke ---------------------------------------------------------------


def _run_cli(args, env_dir) -> "subprocess.CompletedProcess[str]":
    def spawn():
        env = dict(os.environ)
        env["CABINET_CAPTAIN_INBOUND_DIR"] = str(env_dir)
        return subprocess.run(
            [sys.executable, str(CLI)] + args,
            capture_output=True, text=True, timeout=60, env=env)
    return _with_real_popen(spawn)


def test_cli_is_executable():
    assert os.access(CLI, os.X_OK), "captain-inbound.py must ship +x"


def test_cli_latest_get_search_smoke(tmp_path, monkeypatch):
    d = _write_archive(tmp_path, monkeypatch)

    proc = _run_cli(["latest", "-n", "2"], d)
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("tg-777-9")
    assert "onboarding" in lines[0]

    proc = _run_cli(["latest", "--kind", "file"], d)
    assert proc.returncode == 0, proc.stderr
    assert "tg-4242-2" in proc.stdout and "the spec" in proc.stdout

    proc = _run_cli(["get", "tg-4242-2"], d)  # file row → attachment shown
    assert proc.returncode == 0, proc.stderr
    assert "file: egg-spec.pdf (document)" in proc.stdout

    proc = _run_cli(["get", "tg-4242-3"], d)
    assert proc.returncode == 0, proc.stderr
    assert "Ship the EGG til fredag" in proc.stdout
    assert "quoted: the draft plan" in proc.stdout

    proc = _run_cli(["get", "7"], d)  # ambiguous bare mid
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("tg-777-7")
    assert "2 chats match" in proc.stdout and "tg-4242-7" in proc.stdout

    proc = _run_cli(["get", "tg-4242-4242"], d)
    assert proc.returncode == 2
    assert "no archive row matches" in proc.stderr

    proc = _run_cli(["search", "egg", "fredag", "--json"], d)
    assert proc.returncode == 0, proc.stderr
    rows = json.loads(proc.stdout)
    assert [r["dm_id"] for r in rows] == ["tg-4242-3"]
    assert rows[0]["quoted"] == "the draft plan"  # --json = full rows

    proc = _run_cli(["search", "no-such-terms-anywhere"], d)
    assert proc.returncode == 2


def test_cli_semantic_unavailable_exit_code(tmp_path, monkeypatch):
    d = _write_archive(tmp_path, monkeypatch)

    def spawn():
        env = dict(os.environ)
        env["CABINET_CAPTAIN_INBOUND_DIR"] = str(d)
        env["CABINET_MEMORY_SEARCH_SH"] = str(tmp_path / "absent.sh")
        return subprocess.run(
            [sys.executable, str(CLI), "search", "egg", "--semantic"],
            capture_output=True, text=True, timeout=60, env=env)
    proc = _with_real_popen(spawn)
    assert proc.returncode == 2
    assert "semantic search unavailable" in proc.stderr


# --- dir contract ------------------------------------------------------------


def test_default_dir_matches_the_writer(monkeypatch):
    """Reader and writer MUST resolve the same place — the writer's pin is
    the same string (test_inbound_poller_inbound_archive.py)."""
    monkeypatch.delenv("CABINET_CAPTAIN_INBOUND_DIR", raising=False)
    assert captain_inbound.archive_dir().endswith(
        "Library/Application Support/cabinet/captain-inbound")
