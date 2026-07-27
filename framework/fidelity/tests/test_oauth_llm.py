from __future__ import annotations

import json
import subprocess

import pytest

from framework.fidelity import oauth_llm


def _is_claude(argv) -> bool:
    """True for the `claude -p` invocation these tests are actually about.

    The fakes below patch ``subprocess.run`` on the shared subprocess MODULE,
    so they see every subprocess the call makes — including the lane meter's
    ``redis-cli`` (framework/cost/record_lane, wired 2026-07-26 so headless
    Max-pool calls stop being invisible spend). A fake that captures whichever
    subprocess happened to run LAST is asserting about the wrong process; these
    guards keep each assertion pointed at the CLI invocation it names, at
    exactly the strength it had before the meter existed.
    """
    return bool(argv) and argv[0] == "claude"


class TestArgv:
    def test_builds_claude_print_argv_no_api_key(self):
        argv = oauth_llm._build_argv("SYS PROMPT", "claude-sonnet-4-6")
        assert argv[0] == "claude"
        assert "-p" in argv
        assert "--append-system-prompt" in argv
        assert "SYS PROMPT" in argv
        assert "--model" in argv
        assert "claude-sonnet-4-6" in argv

    def test_argv_never_references_anthropic_api_key(self):
        argv = oauth_llm._build_argv("SYS", "claude-sonnet-4-6")
        assert all("ANTHROPIC_API_KEY" not in a for a in argv)


class TestRawLlm:
    def test_returns_stdout_text(self, monkeypatch):
        def fake_run(argv, **kw):
            assert argv[0] == "claude"
            assert "ANTHROPIC_API_KEY" not in kw.get("env", {})
            return subprocess.CompletedProcess(argv, 0, stdout="hello reply", stderr="")
        monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
        out = oauth_llm.oauth_raw_llm("payload", "system")
        assert out == "hello reply"

    def test_returns_none_on_nonzero_exit(self, monkeypatch):
        def fake_run(argv, **kw):
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="quota")
        monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
        assert oauth_llm.oauth_raw_llm("p", "s") is None

    def test_returns_none_on_timeout(self, monkeypatch):
        def fake_run(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 185)
        monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
        assert oauth_llm.oauth_raw_llm("p", "s") is None

    def test_returns_none_when_cli_missing(self, monkeypatch):
        def fake_run(argv, **kw):
            raise FileNotFoundError("claude not on PATH")
        monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
        assert oauth_llm.oauth_raw_llm("p", "s") is None

    def test_drops_user_setting_source_to_close_global_leak(self):
        # USER-GLOBAL leak fix: --setting-sources project,local omits `user`, so
        # ~/.claude/CLAUDE.md (screenpipe-memories) + memory are NOT loaded.
        # Verified live 2026-06-19: Bakery probe -> UNKNOWN with the flag,
        # AUTH_OK still works (HOME/keychain untouched).
        argv = oauth_llm._build_argv("SYS", "claude-sonnet-4-6")
        assert "--setting-sources" in argv
        i = argv.index("--setting-sources")
        sources = argv[i + 1].split(",")
        assert "user" not in sources, "the `user` source leaks ~/.claude/CLAUDE.md"
        assert "project" in sources and "local" in sources

    def test_does_not_override_home(self, monkeypatch):
        # HOME must stay intact — the macOS keychain/OAuth is HOME-anchored;
        # overriding it breaks auth (keychain-not-found). No CABINET_EVAL_HOME.
        import os
        captured = {}

        def fake_run(argv, **kw):
            if _is_claude(argv):
                captured["home"] = kw.get("env", {}).get("HOME")
            return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

        monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
        oauth_llm.oauth_raw_llm("p", "s")
        assert captured["home"] == os.environ.get("HOME")

    def test_runs_in_isolated_cwd_not_project(self, monkeypatch):
        """LEAK ISOLATION (regression guard): the eval `claude -p` must run in
        an isolated temp cwd, NEVER the cabinet project root — otherwise it
        auto-discovers CLAUDE.md / .remember (post-cutoff, this-session
        context = an out-of-band leak past the payload-level cutoff fence).
        Verified live 2026-06-19: cabinet-cwd leaked the held-out answer;
        clean-cwd returned UNKNOWN."""
        import os
        captured = {}

        def fake_run(argv, **kw):
            if _is_claude(argv):
                captured["cwd"] = kw.get("cwd")
            return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

        monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
        oauth_llm.oauth_raw_llm("payload", "system")
        cwd = captured["cwd"]
        assert cwd and os.path.isdir(cwd), "eval claude -p must run with an explicit temp cwd"
        assert "fidelity_eval_clean" in os.path.basename(cwd)
        assert not os.path.exists(os.path.join(cwd, "CLAUDE.md")), "cwd must not expose a CLAUDE.md"
        assert not os.path.exists(os.path.join(cwd, ".remember")), "cwd must not expose .remember"


def _envelope(structured=None, result=None, cost=0.0123, is_error=False):
    """Minimal `claude -p --output-format json` result envelope."""
    env = {"type": "result", "subtype": "success", "is_error": is_error,
           "total_cost_usd": cost, "session_id": "s-1"}
    if structured is not None:
        env["structured_output"] = structured
    if result is not None:
        env["result"] = result
    return json.dumps(env)


class TestJsonLlm:
    """AUD-11 (audit #31): oauth_json_llm uses --output-format json
    --json-schema; the CLI enforces the JSON contract structurally, the old
    2-attempt parse-retry loop is gone, and total_cost_usd is captured as a
    supplementary B5.8 signal. Auth stays OAuth-only (no --bare, no API key)."""

    def test_argv_uses_output_format_json_and_json_schema(self, monkeypatch):
        captured = {}

        def fake_run(argv, **kw):
            if _is_claude(argv):
                captured["argv"] = argv
                captured["env"] = kw.get("env", {})
            return subprocess.CompletedProcess(
                argv, 0, stdout=_envelope(structured={"verdict": "match"}), stderr="")

        monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
        out = oauth_llm.oauth_json_llm("payload", "system")
        assert out == {"verdict": "match"}
        argv = captured["argv"]
        i = argv.index("--output-format")
        assert argv[i + 1] == "json"
        j = argv.index("--json-schema")
        assert json.loads(argv[j + 1]) == {"type": "object"}
        # OAuth-only discipline unchanged: no API key in child env, user
        # setting-source still dropped.
        assert "ANTHROPIC_API_KEY" not in captured["env"]
        k = argv.index("--setting-sources")
        assert "user" not in argv[k + 1].split(",")

    def test_returns_structured_output_dict(self, monkeypatch):
        verdict = {"verdict": "match", "rationale": "same call",
                   "what_diverged": "", "real_decision": "ok", "draft_decision": "ok"}
        monkeypatch.setattr(
            oauth_llm.subprocess, "run",
            lambda argv, **kw: subprocess.CompletedProcess(
                argv, 0, stdout=_envelope(structured=verdict), stderr=""))
        assert oauth_llm.oauth_json_llm("payload", "system") == verdict

    def test_single_subprocess_call_no_retry_loop(self, monkeypatch):
        calls = {"n": 0}

        def fake_run(argv, **kw):
            if _is_claude(argv):
                calls["n"] += 1
            return subprocess.CompletedProcess(argv, 0, stdout="garbage", stderr="")

        monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
        assert oauth_llm.oauth_json_llm("p", "s") is None
        assert calls["n"] == 1  # parse-retry loop removed (AUD-11)

    def test_custom_schema_passthrough(self, monkeypatch):
        captured = {}
        schema = {"type": "object", "properties": {"verdict": {"type": "string"}},
                  "required": ["verdict"]}

        def fake_run(argv, **kw):
            if _is_claude(argv):
                captured["argv"] = argv
            return subprocess.CompletedProcess(
                argv, 0, stdout=_envelope(structured={"verdict": "match"}), stderr="")

        monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
        oauth_llm.oauth_json_llm("p", "s", schema=schema)
        j = captured["argv"].index("--json-schema")
        assert json.loads(captured["argv"][j + 1]) == schema

    def test_fallback_parses_fenced_result_once(self, monkeypatch):
        # Defensive single-pass fallback: no structured_output, fenced JSON in
        # `result` (older CLI shape) still parses — but with NO retry loop.
        verdict = {"verdict": "match"}
        monkeypatch.setattr(
            oauth_llm.subprocess, "run",
            lambda argv, **kw: subprocess.CompletedProcess(
                argv, 0,
                stdout=_envelope(result="```json\n" + json.dumps(verdict) + "\n```"),
                stderr=""))
        assert oauth_llm.oauth_json_llm("payload", "system") == verdict

    def test_returns_none_on_error_envelope(self, monkeypatch):
        monkeypatch.setattr(
            oauth_llm.subprocess, "run",
            lambda argv, **kw: subprocess.CompletedProcess(
                argv, 0, stdout=_envelope(structured={"x": 1}, is_error=True),
                stderr=""))
        assert oauth_llm.oauth_json_llm("p", "s") is None

    def test_returns_none_on_nonzero_exit(self, monkeypatch):
        monkeypatch.setattr(
            oauth_llm.subprocess, "run",
            lambda argv, **kw: subprocess.CompletedProcess(argv, 1, stdout="", stderr="quota"))
        assert oauth_llm.oauth_json_llm("p", "s") is None

    def test_returns_none_on_unparseable_stdout(self, monkeypatch):
        monkeypatch.setattr(
            oauth_llm.subprocess, "run",
            lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout="not json", stderr=""))
        assert oauth_llm.oauth_json_llm("p", "s") is None

    def test_captures_total_cost_usd(self, monkeypatch):
        monkeypatch.setattr(
            oauth_llm.subprocess, "run",
            lambda argv, **kw: subprocess.CompletedProcess(
                argv, 0, stdout=_envelope(structured={"v": 1}, cost=0.25), stderr=""))
        before_total = oauth_llm.TOTAL_COST_USD
        oauth_llm.oauth_json_llm("p", "s")
        assert oauth_llm.LAST_COST_USD == 0.25
        assert oauth_llm.TOTAL_COST_USD == pytest.approx(before_total + 0.25)

    def test_runs_in_isolated_cwd(self, monkeypatch):
        import os
        captured = {}

        def fake_run(argv, **kw):
            if _is_claude(argv):
                captured["cwd"] = kw.get("cwd")
            return subprocess.CompletedProcess(
                argv, 0, stdout=_envelope(structured={"v": 1}), stderr="")

        monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
        oauth_llm.oauth_json_llm("p", "s")
        assert captured["cwd"] and os.path.isdir(captured["cwd"])
        assert "fidelity_eval_clean" in os.path.basename(captured["cwd"])
