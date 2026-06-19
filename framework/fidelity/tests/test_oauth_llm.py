from __future__ import annotations

import json
import subprocess

import pytest

from framework.fidelity import oauth_llm


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
            captured["cwd"] = kw.get("cwd")
            return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

        monkeypatch.setattr(oauth_llm.subprocess, "run", fake_run)
        oauth_llm.oauth_raw_llm("payload", "system")
        cwd = captured["cwd"]
        assert cwd and os.path.isdir(cwd), "eval claude -p must run with an explicit temp cwd"
        assert "fidelity_eval_clean" in os.path.basename(cwd)
        assert not os.path.exists(os.path.join(cwd, "CLAUDE.md")), "cwd must not expose a CLAUDE.md"
        assert not os.path.exists(os.path.join(cwd, ".remember")), "cwd must not expose .remember"


class TestJsonLlm:
    def test_parses_json_verdict(self, monkeypatch):
        verdict = {"verdict": "match", "rationale": "same call",
                   "what_diverged": "", "real_decision": "ok", "draft_decision": "ok"}
        monkeypatch.setattr(oauth_llm, "oauth_raw_llm",
                            lambda p, s, max_tokens=400, model="claude-sonnet-4-6":
                            "```json\n" + json.dumps(verdict) + "\n```")
        out = oauth_llm.oauth_json_llm("payload", "system")
        assert out == verdict

    def test_returns_none_when_unparseable(self, monkeypatch):
        monkeypatch.setattr(oauth_llm, "oauth_raw_llm",
                            lambda p, s, max_tokens=400, model="claude-sonnet-4-6": "not json")
        assert oauth_llm.oauth_json_llm("p", "s") is None

    def test_retries_once_on_transient_unparseable(self, monkeypatch):
        # Transient flake: first call returns non-JSON, second returns valid —
        # the retry must absorb it (this was the live intent_verdict='error').
        verdict = {"verdict": "match"}
        calls = {"n": 0}

        def flaky(p, s, max_tokens=400, model="claude-sonnet-4-6"):
            calls["n"] += 1
            return "garbage" if calls["n"] == 1 else "```json\n" + json.dumps(verdict) + "\n```"

        monkeypatch.setattr(oauth_llm, "oauth_raw_llm", flaky)
        out = oauth_llm.oauth_json_llm("p", "s")
        assert out == verdict
        assert calls["n"] == 2  # retried exactly once
