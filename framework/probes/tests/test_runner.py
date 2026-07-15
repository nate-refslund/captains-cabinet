"""Probe deploy shell (runner.py) — fixtured; the real clients are NEVER built
here (probe doctrine: a probe must never hit a live API in a test).

Pins (lane-supply 2026-07-05): the CABINET_PROBES_ENABLED guard actually
guards; empty API keys skip probe-wide (empty env values never claim keys);
missing checkouts skip per-product with visible reasons; the sentry seen-state
round-trips through the env-overridable state dir and is NOT persisted on
dry runs; probe_main's dry-run wires the collector emit (zero writes)."""
from __future__ import annotations

import json

from framework.probes import correlation as c
from framework.probes import runner


class _FakeGh:
    """Same surface as probe_github.GhClient; canned fixtures."""

    def __init__(self, prs=None):
        self._prs = prs or []

    def trailer_prs(self, repo):
        return self._prs

    def pr_view(self, repo, number):
        return {"state": "MERGED", "mergedAt": "2026-07-05T00:00:00Z",
                "statusCheckRollup": [{"conclusion": "SUCCESS"}]}

    def reverts(self, repo):
        return set()

    def local_commits_since(self, window="1 hour ago"):
        return []


def _cfg(tmp_path, **over):
    checkout = tmp_path / "product"
    checkout.mkdir(exist_ok=True)
    base = {"github": [{"repo": "org/app", "checkout": str(checkout)}],
            "vercel": [{"app": "app", "checkout": str(checkout)}],
            "sentry": {"org": "org", "projects": [
                {"project": "app", "checkout": str(checkout)}]}}
    base.update(over)
    return base


def test_probes_enabled_only_on_literal_1(monkeypatch):
    monkeypatch.delenv("CABINET_PROBES_ENABLED", raising=False)
    assert runner.probes_enabled() is False
    monkeypatch.setenv("CABINET_PROBES_ENABLED", "true")
    assert runner.probes_enabled() is False   # fail-closed: only "1" enables
    monkeypatch.setenv("CABINET_PROBES_ENABLED", "1")
    assert runner.probes_enabled() is True


def test_missing_config_file_is_empty_noop(tmp_path):
    assert runner.load_config(tmp_path / "absent.yml") == {}


def test_github_missing_checkout_skips_fail_closed(tmp_path):
    cfg = {"github": [{"repo": "org/app", "checkout": str(tmp_path / "gone")}]}
    out = runner.run_github_products(cfg, client_factory=_FakeGh,
                                     emit=lambda **e: (_ for _ in ()).throw(
                                         AssertionError("must not emit")),
                                     hc=lambda *a, **k: None,
                                     chdir=lambda p: None)
    assert out[0]["skipped"].startswith("checkout missing")


def test_github_runs_probe_in_checkout_and_reports(tmp_path):
    cid = c.mint()
    prs = [{"number": 7, "body": c.git_trailer(cid), "merge_sha": None}]
    emitted, chdirs = [], []
    out = runner.run_github_products(
        _cfg(tmp_path), client_factory=lambda: _FakeGh(prs),
        emit=lambda **e: emitted.append(e) or {"emitted": True},
        hc=lambda *a, **k: None, chdir=chdirs.append, rows=[])
    # rows=[] → the cid is unattributable (RT#3) → run_probe skips it; the
    # point pinned HERE is the shell: chdir happened, probe ran, shape returned.
    assert chdirs == [str(tmp_path / "product")]
    assert out[0]["repo"] == "org/app" and out[0]["fresh"] is True


def test_dry_run_collector_survives_a_real_join(tmp_path):
    """Regression (2026-07-05 self-review): the probe ``emit`` param is
    lib.emit_outcome (returns {emitted: bool}), so the dry-run collector must
    preserve that contract. A bare append-collector returns None and crashes
    run_probe's res.get('emitted') the instant an artifact actually joins —
    exercise THAT path (a merged PR whose cid resolves to a decided proposal)."""
    from framework.acting import loop
    cid = c.mint()
    prop = loop.proposal_event(actor={"kind": "officer", "id": "cos"},
                               lane="feature", subject="s",
                               ts="2026-07-05T01:00:00Z", refs=[c.ref_for(cid)])
    prop["proposal"]["decision"] = "approved"
    prop["proposal"]["decided_at"] = "2026-07-05T01:00:00Z"
    prs = [{"number": 7, "body": c.git_trailer(cid), "merge_sha": None}]
    probe_emit, sink = runner._collector()   # the real dry-run collector
    out = runner.run_github_products(
        _cfg(tmp_path), client_factory=lambda: _FakeGh(prs),
        emit=probe_emit, hc=runner._noop_hc,
        chdir=lambda p: None, rows=[prop])
    # merged PR joined its proposal → the collector captured the outcome write,
    # run_probe saw a truthy {emitted: True}, and NOTHING crashed / hit a ledger.
    assert out[0]["emitted"] and out[0]["emitted"][0]["status"] == "ok"
    assert len(sink) == 1 and sink[0]["outcome"]["status"] == "ok"


def test_vercel_empty_key_skips_probe_wide(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL_API_KEY", "")   # empty placeholder = absent
    out = runner.run_vercel_products(_cfg(tmp_path),
                                     client_factory=lambda: None)
    assert "VERCEL_API_KEY unset/empty" in out[0]["skipped"]


def test_vercel_team_scope_is_passed_per_deployment(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL_API_KEY", "fixture-token")
    cfg = _cfg(tmp_path)
    cfg["vercel"][0]["team_id"] = "team_second_captain"
    seen = []

    class _FakeVercel:
        def deployments(self, product, limit=50):
            return []
        def local_commits_since(self, window="15 minutes ago"):
            return []
        def rolled_back_uids(self, product, since_days=14):
            return set()
        def now_ms(self):
            return 0

    out = runner.run_vercel_products(
        cfg,
        client_factory=lambda **kw: seen.append(kw) or _FakeVercel(),
        emit=lambda **kw: None,
        hc=lambda *a, **kw: None,
        chdir=lambda p: None,
        rows=[],
    )
    assert seen == [{"team_id": "team_second_captain"}]
    assert out[0]["fresh"] is True


def test_sentry_empty_token_skips_probe_wide(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTRY_AUTH_TOKEN", "")
    out = runner.run_sentry_products(_cfg(tmp_path),
                                     client_factory=lambda **k: None)
    assert "SENTRY_AUTH_TOKEN unset/empty" in out[0]["skipped"]


def test_sentry_seen_state_roundtrip_env_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(runner.STATE_DIR_ENV, str(tmp_path))
    runner.save_sentry_seen({"app": {"v1": "2026-07-05T00:00:00Z"}})
    assert runner.load_sentry_seen() == {"app": {"v1": "2026-07-05T00:00:00Z"}}
    assert (tmp_path / runner.SENTRY_SEEN_FILE).exists()


def test_sentry_persist_state_false_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(runner.STATE_DIR_ENV, str(tmp_path))
    monkeypatch.setenv("SENTRY_AUTH_TOKEN", "t")

    class _FakeSentry:
        def __init__(self, org):
            self.org = org

        def release_stats(self, org, project):
            return []

        def baseline(self, org, project):
            return None

        def local_commits_since(self, window="1 hour ago"):
            return []

    out = runner.run_sentry_products(
        _cfg(tmp_path), client_factory=lambda **k: _FakeSentry(k.get("org")),
        emit=lambda **e: {"emitted": False}, hc=lambda *a, **k: None,
        chdir=lambda p: None, persist_state=False)
    assert out[0]["fresh"] is True
    assert not (tmp_path / runner.SENTRY_SEEN_FILE).exists()   # dry: no clock advance


def test_probe_main_disabled_exits_zero(monkeypatch, capsys):
    monkeypatch.delenv("CABINET_PROBES_ENABLED", raising=False)
    rc = runner.probe_main("github", runner.run_github_products, _FakeGh, argv=[])
    assert rc == 0 and "disabled" in capsys.readouterr().out


def test_probe_main_dry_run_reports_would_write(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("CABINET_PROBES_ENABLED", raising=False)  # dry needs no flag
    cfgp = tmp_path / "probes.yml"
    checkout = tmp_path / "product"
    checkout.mkdir()
    cfgp.write_text(json.dumps(   # yaml parses json — no yaml dep in the test
        {"github": [{"repo": "org/app", "checkout": str(checkout)}]}))
    monkeypatch.setattr(runner.os, "chdir", lambda p: None)
    rc = runner.probe_main("github", runner.run_github_products,
                           lambda: _FakeGh(), argv=["--dry-run",
                                                    "--config", str(cfgp)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["mode"] == "dry-run" and out["would_write"] == 0


def test_probe_main_error_is_fail_closed(monkeypatch, capsys):
    monkeypatch.setenv("CABINET_PROBES_ENABLED", "1")

    def boom(cfg, **kw):
        raise RuntimeError("source exploded")

    rc = runner.probe_main("github", boom, _FakeGh, argv=[])
    assert rc == 1
    assert "no verdicts emitted" in capsys.readouterr().err
