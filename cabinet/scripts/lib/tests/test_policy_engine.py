"""Tests for the Cabinet Policy Engine.

Covers:
1. All adversary bypass patterns from pre-tool-use.sh v3.0-v3.7.2
2. False positive guards — legitimate commands that must NOT be blocked
3. Policy loading — framework + preset layering
4. Path blocks — constitution, .env, infrastructure, tier2 isolation
5. Officer exemptions — CTO allowed product code, CoS allowed infrastructure
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure the lib directory is importable
_LIB_DIR = Path(__file__).parent.parent.resolve()
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

# Ensure real yaml is available (conftest.py may stub it for ETL tests).
# Force-import the real yaml module before importing policy_engine.
if "yaml" in sys.modules:
    _yaml_mod = sys.modules["yaml"]
    if not hasattr(_yaml_mod, "safe_load"):
        # The stub from conftest.py is loaded — replace with real yaml
        del sys.modules["yaml"]
        import yaml  # noqa: E402
        sys.modules["yaml"] = yaml

from policy_engine import (
    extract_invoked_binaries,
    is_destructive_rm,
    check_bash_write_to_path,
    evaluate_policy,
    load_policies,
    _path_matches_pattern,
    _strip_quotes_and_escapes,
)


# ===================================================================
# 1. BINARY DETECTION — Adversary bypass patterns from v3.0-v3.7.2
# ===================================================================

class TestExtractInvokedBinaries:
    """Test extract_invoked_binaries against all known bypass patterns."""

    # --- Direct invocation ---

    def test_direct_invocation(self):
        assert "sudo" in extract_invoked_binaries("sudo ls")

    def test_direct_docker(self):
        assert "docker" in extract_invoked_binaries("docker run ubuntu")

    def test_direct_systemctl(self):
        assert "systemctl" in extract_invoked_binaries("systemctl restart nginx")

    def test_direct_shutdown(self):
        assert "shutdown" in extract_invoked_binaries("shutdown -h now")

    def test_direct_reboot(self):
        assert "reboot" in extract_invoked_binaries("reboot")

    def test_direct_halt(self):
        assert "halt" in extract_invoked_binaries("halt")

    # --- v3.6 B5: Full path invocation ---

    def test_full_path_sudo(self):
        assert "sudo" in extract_invoked_binaries("/usr/bin/sudo ls")

    def test_full_path_reboot(self):
        assert "reboot" in extract_invoked_binaries("/sbin/reboot")

    def test_full_path_rm(self):
        assert "rm" in extract_invoked_binaries("/bin/rm -rf /")

    def test_full_path_shutdown(self):
        assert "shutdown" in extract_invoked_binaries("/usr/sbin/shutdown -h now")

    # --- v3.4 BUG 2 / v3.5: Shell wrapping (bash -c, sh -c) ---

    def test_bash_c_sudo(self):
        assert "sudo" in extract_invoked_binaries("bash -c 'sudo ls'")

    def test_sh_c_docker(self):
        assert "docker" in extract_invoked_binaries("sh -c 'docker run ubuntu'")

    def test_bash_xc_sudo(self):
        """v3.4 BUG 2: compound flag -xc."""
        assert "sudo" in extract_invoked_binaries("bash -xc 'sudo ls'")

    def test_bash_lc_sudo(self):
        """v3.4 BUG 2: compound flag -lc."""
        assert "sudo" in extract_invoked_binaries("bash -lc 'sudo ls'")

    def test_bash_login_c_sudo(self):
        """v3.4 BUG 2: long flag --login -c."""
        assert "sudo" in extract_invoked_binaries("bash --login -c 'sudo ls'")

    def test_bash_norc_c_sudo(self):
        """v3.4 BUG 2: long flag --norc -c."""
        assert "sudo" in extract_invoked_binaries("bash --norc -c 'sudo ls'")

    def test_bash_x_c_sudo(self):
        """v3.5 BUG-1: bash -x -c (split flags)."""
        assert "sudo" in extract_invoked_binaries("bash -x -c 'sudo ls'")

    def test_bash_C_c_sudo(self):
        """v3.5 BUG-1: bash -C -c (uppercase C flag)."""
        assert "sudo" in extract_invoked_binaries("bash -C -c 'sudo ls'")

    # --- v3.6 B4: Here-string (<<<) ---

    def test_bash_herestring_quoted(self):
        assert "sudo" in extract_invoked_binaries("bash <<<'sudo ls'")

    def test_bash_herestring_bare(self):
        """v3.6 B4: bare (no quote) here-string."""
        assert "sudo" in extract_invoked_binaries("bash <<<sudo")

    def test_sh_herestring(self):
        assert "docker" in extract_invoked_binaries("sh <<<'docker run'")

    # --- v3.5 H1: Heredoc body ---

    def test_bash_heredoc_sudo(self):
        cmd = "bash <<EOF\nsudo ls\nEOF"
        assert "sudo" in extract_invoked_binaries(cmd)

    def test_sh_heredoc_docker(self):
        cmd = "sh <<DELIM\ndocker run ubuntu\nDELIM"
        assert "docker" in extract_invoked_binaries(cmd)

    # --- v3.4 H1 / v3.5 H2/H3: Eval wrapping ---

    def test_eval_sudo(self):
        assert "sudo" in extract_invoked_binaries("eval 'sudo ls'")

    def test_eval_env_sudo(self):
        """v3.4 H1: eval 'env sudo ls'."""
        assert "sudo" in extract_invoked_binaries("eval 'env sudo ls'")

    def test_eval_nohup_sudo(self):
        assert "sudo" in extract_invoked_binaries("eval 'nohup sudo ls'")

    def test_eval_exec_sudo(self):
        assert "sudo" in extract_invoked_binaries("eval 'exec sudo ls'")

    def test_eval_time_sudo(self):
        assert "sudo" in extract_invoked_binaries("eval 'time sudo ls'")

    def test_eval_eval_sudo(self):
        """v3.5 H2: double-eval nesting."""
        assert "sudo" in extract_invoked_binaries("eval 'eval sudo ls'")

    def test_eval_bash_c_sudo(self):
        """v3.5 H3: eval of shell command."""
        assert "sudo" in extract_invoked_binaries("eval 'bash -c sudo ls'")

    def test_eval_compound_sudo(self):
        """v3.7: eval 'echo ok; sudo ls' — compound inside eval."""
        assert "sudo" in extract_invoked_binaries("eval 'echo ok; sudo ls'")

    # --- Wrapper commands ---

    def test_env_sudo(self):
        assert "sudo" in extract_invoked_binaries("env sudo ls")

    def test_env_var_sudo(self):
        assert "sudo" in extract_invoked_binaries("env FOO=bar sudo ls")

    def test_nohup_sudo(self):
        assert "sudo" in extract_invoked_binaries("nohup sudo ls")

    def test_exec_sudo(self):
        assert "sudo" in extract_invoked_binaries("exec sudo ls")

    def test_time_sudo(self):
        assert "sudo" in extract_invoked_binaries("time sudo ls")

    def test_timeout_sudo(self):
        assert "sudo" in extract_invoked_binaries("timeout 10 sudo ls")

    def test_nice_sudo(self):
        assert "sudo" in extract_invoked_binaries("nice -n 10 sudo ls")

    def test_ionice_sudo(self):
        assert "sudo" in extract_invoked_binaries("ionice -c 3 sudo ls")

    def test_stdbuf_sudo(self):
        assert "sudo" in extract_invoked_binaries("stdbuf -oL sudo ls")

    def test_setsid_sudo(self):
        assert "sudo" in extract_invoked_binaries("setsid sudo ls")

    def test_chroot_sudo(self):
        assert "sudo" in extract_invoked_binaries("chroot / sudo ls")

    # --- v3.4 H2: env backslash escape ---

    def test_env_backslash_sudo(self):
        """v3.4 H2: env \\sudo ls — backslash before keyword."""
        assert "sudo" in extract_invoked_binaries("env \\sudo ls")

    # --- v3.5 BUG-3: Leading backslash before wrapper ---

    def test_backslash_eval_sudo(self):
        """v3.5 BUG-3: \\eval 'sudo'."""
        assert "sudo" in extract_invoked_binaries("\\eval 'sudo ls'")

    def test_backslash_nohup_sudo(self):
        assert "sudo" in extract_invoked_binaries("\\nohup sudo ls")

    def test_backslash_env_sudo(self):
        assert "sudo" in extract_invoked_binaries("\\env sudo ls")

    # --- v3.7 post-adversary Finding 2: Quote splicing ---

    def test_quoted_sudo(self):
        """Direct: "sudo" ls."""
        assert "sudo" in extract_invoked_binaries('"sudo" ls')

    def test_quote_splice_sudo(self):
        """Quote splice: s"udo" ls."""
        assert "sudo" in extract_invoked_binaries('s"udo" ls')

    def test_double_quote_splice(self):
        """Double splice: "su""do" ls."""
        assert "sudo" in extract_invoked_binaries('"su""do" ls')

    def test_single_quote_splice(self):
        """Single-quote splice: s'udo' ls."""
        assert "sudo" in extract_invoked_binaries("s'udo' ls")

    # --- v3.7.2 BSQ: Backslash-escaped quote splice ---

    def test_bsq_backslash_dquote_sudo(self):
        r"""v3.7.2: echo hi;\"sudo\" ls."""
        assert "sudo" in extract_invoked_binaries('echo hi;\\"sudo\\" ls')

    # --- v3.3: Brace expansion ---

    def test_brace_comma_sudo(self):
        """v3.3: {,sudo} ls — empty-first-element brace."""
        assert "sudo" in extract_invoked_binaries("{,sudo} ls")

    def test_brace_sudo_comma(self):
        """v3.3: {sudo,} ls — keyword-first brace."""
        assert "sudo" in extract_invoked_binaries("{sudo,} ls")

    def test_brace_nested(self):
        """v3.7: {,{,sudo}} — nested brace."""
        assert "sudo" in extract_invoked_binaries("{,{,sudo}} ls")

    # --- v3.6 B10: Trailing comma in brace ---

    def test_brace_trailing_comma(self):
        """v3.6 B10: {,sudo,} — trailing comma."""
        assert "sudo" in extract_invoked_binaries("{,sudo,} ls")

    # --- Compound commands ---

    def test_semicolon_compound(self):
        assert "sudo" in extract_invoked_binaries("echo ok; sudo ls")

    def test_and_compound(self):
        assert "sudo" in extract_invoked_binaries("true && sudo ls")

    def test_or_compound(self):
        assert "sudo" in extract_invoked_binaries("false || sudo ls")

    def test_pipe_compound(self):
        assert "sudo" in extract_invoked_binaries("echo x | sudo tee file")

    def test_subshell_sudo(self):
        """v3.6 BYPASS 2: eval '(sudo)'."""
        assert "sudo" in extract_invoked_binaries("(sudo ls)")

    def test_brace_group_sudo(self):
        """v3.6 BYPASS 2: eval '{ sudo; }'."""
        assert "sudo" in extract_invoked_binaries("{ sudo ls; }")

    def test_negation_sudo(self):
        """v3.6 BYPASS 2: ! sudo ls."""
        assert "sudo" in extract_invoked_binaries("! sudo ls")

    # --- v3.3 env-S: env -S flag ---

    def test_env_s_sudo(self):
        """v3.7: env -S'sudo ls'."""
        assert "sudo" in extract_invoked_binaries("env -S'sudo ls'")

    # --- v3.6 BYPASS 4: Additional shells ---

    def test_mksh_c_sudo(self):
        assert "sudo" in extract_invoked_binaries("mksh -c 'sudo ls'")

    def test_fish_c_sudo(self):
        assert "sudo" in extract_invoked_binaries("fish -c 'sudo ls'")

    def test_dash_c_sudo(self):
        assert "sudo" in extract_invoked_binaries("dash -c 'sudo ls'")

    def test_zsh_c_sudo(self):
        assert "sudo" in extract_invoked_binaries("zsh -c 'sudo ls'")

    def test_ksh_c_sudo(self):
        assert "sudo" in extract_invoked_binaries("ksh -c 'sudo ls'")

    # --- v3.6 B6: Long flags with arguments ---

    def test_bash_rcfile_c_sudo(self):
        """v3.6 B6: bash --rcfile FILE -c 'sudo'."""
        assert "sudo" in extract_invoked_binaries("bash --rcfile /tmp/rc -c 'sudo ls'")

    # --- v3.4 H3 / COMMAND_PREAMBLE ---

    def test_command_p_sudo(self):
        """command -p sudo — executes sudo."""
        assert "sudo" in extract_invoked_binaries("command -p sudo ls")

    def test_command_p_dashdash_sudo(self):
        """v3.4 H3: command -p -- sudo ls."""
        assert "sudo" in extract_invoked_binaries("command -p -- sudo ls")

    def test_command_dashdash_sudo(self):
        """command -- sudo ls."""
        assert "sudo" in extract_invoked_binaries("command -- sudo ls")

    # --- Nested combinations ---

    def test_nested_eval_bash_c_env_sudo(self):
        """Deeply nested: eval 'bash -c \"env sudo ls\"'."""
        assert "sudo" in extract_invoked_binaries("eval 'bash -c \"env sudo ls\"'")

    def test_compound_then_wrapper_then_target(self):
        """echo ok && env sudo ls."""
        assert "sudo" in extract_invoked_binaries("echo ok && env sudo ls")

    def test_inline_var_sudo(self):
        """FOO=bar sudo ls — POSIX inline variable assignment."""
        assert "sudo" in extract_invoked_binaries("FOO=bar sudo ls")

    def test_multiple_inline_vars_sudo(self):
        """FOO=bar BAZ=qux sudo ls."""
        assert "sudo" in extract_invoked_binaries("FOO=bar BAZ=qux sudo ls")

    # --- Backslash escape (v3.5 BUG-3 extended) ---

    def test_backslash_sudo(self):
        """\\sudo ls — shell treats \\sudo as sudo."""
        assert "sudo" in extract_invoked_binaries("\\sudo ls")


# ===================================================================
# 2. FALSE POSITIVE GUARDS — legitimate commands must NOT be blocked
# ===================================================================

class TestFalsePositiveGuards:
    """Legitimate commands that must NOT trigger binary_block."""

    # Policy for testing
    BLOCK_POLICY = {
        "name": "test-block",
        "type": "binary_block",
        "binaries": ["sudo", "docker", "systemctl", "shutdown", "reboot", "halt"],
        "message": "System-level command not permitted",
    }

    def _eval(self, command: str) -> str | None:
        return evaluate_policy(
            self.BLOCK_POLICY,
            "Bash",
            {"command": command},
            "cto",
        )

    def test_grep_mention(self):
        """grep -E 'sudo|docker' file — data-context mention."""
        assert self._eval("grep -E 'sudo|docker' file") is None

    def test_echo_mention(self):
        """echo "sudo ls" — string argument, not execution."""
        assert self._eval('echo "sudo ls"') is None

    def test_cat_file(self):
        """cat /workspace/product/file — read, not write."""
        assert self._eval("cat /workspace/product/file") is None

    def test_ls_filename(self):
        """ls docker-compose.yml — filename mention, not execution."""
        assert self._eval("ls docker-compose.yml") is None

    def test_git_commit_message(self):
        """git commit -m "staged && git push origin main" — mention in commit msg."""
        # The word 'sudo' doesn't appear here, so it shouldn't block
        assert self._eval('git commit -m "sudo is blocked"') is None

    def test_rm_regular_file(self):
        """rm file.txt — non-recursive, non-root."""
        assert self._eval("rm file.txt") is None

    def test_command_v_sudo(self):
        """command -v sudo — introspection, not execution."""
        assert self._eval("command -v sudo") is None

    def test_command_V_sudo(self):
        """command -V sudo — introspection."""
        assert self._eval("command -V sudo") is None

    def test_which_sudo(self):
        """which sudo — query, not execution."""
        assert self._eval("which sudo") is None

    def test_cat_shutdown_md(self):
        """cat shutdown.md — reading a file, not executing shutdown."""
        assert self._eval("cat shutdown.md") is None

    def test_grep_docker_file(self):
        """grep docker file.txt — searching for text, not executing docker."""
        assert self._eval("grep docker file.txt") is None

    def test_echo_docker_compose(self):
        """echo 'docker-compose up' — echoing text."""
        assert self._eval("echo 'docker-compose up'") is None

    def test_man_sudo(self):
        """man sudo — reading documentation."""
        assert self._eval("man sudo") is None


# ===================================================================
# 3. DESTRUCTIVE RM DETECTION
# ===================================================================

class TestDestructiveRm:
    """Test is_destructive_rm against v3.6 B7/B8/B9 flag patterns."""

    def test_rm_rf_root(self):
        assert is_destructive_rm("rm -rf /")

    def test_rm_fr_root(self):
        """v3.6 B7: rm -fr /."""
        assert is_destructive_rm("rm -fr /")

    def test_rm_f_r_root(self):
        """v3.6 B8: rm -f -r / (split flags)."""
        assert is_destructive_rm("rm -f -r /")

    def test_rm_recursive_force_root(self):
        """v3.6 B9: rm --recursive --force /."""
        assert is_destructive_rm("rm --recursive --force /")

    def test_rm_rf_root_star(self):
        """rm -rf /* — wildcard root."""
        assert is_destructive_rm("rm -rf /*")

    def test_rm_R_root(self):
        """rm -R / — uppercase R flag."""
        assert is_destructive_rm("rm -R /")

    def test_rm_rf_tmp(self):
        """rm -rf /tmp/build — non-root, should NOT trigger."""
        assert not is_destructive_rm("rm -rf /tmp/build")

    def test_rm_regular_file(self):
        """rm file.txt — no recursive flag."""
        assert not is_destructive_rm("rm file.txt")

    def test_rm_no_recursive(self):
        """rm -f / — force but no recursive."""
        assert not is_destructive_rm("rm -f /some/file")

    def test_rm_rf_compound(self):
        """echo ok; rm -rf / — compound statement."""
        assert is_destructive_rm("echo ok; rm -rf /")

    def test_rm_rf_root_quoted(self):
        """rm -rf '/' — quoted root path."""
        assert is_destructive_rm("rm -rf '/'")


# ===================================================================
# 4. COMMAND_CONTAINS POLICY
# ===================================================================

class TestCommandContains:
    """Test command_contains policy type."""

    def test_vercel_deploy_blocked(self):
        policy = {
            "name": "no-deploy",
            "type": "command_contains",
            "tool": "Bash",
            "patterns": ["vercel deploy", "vercel --prod"],
            "message": "No production deploy",
        }
        result = evaluate_policy(policy, "Bash", {"command": "vercel deploy"}, "cto")
        assert result is not None
        assert "No production deploy" in result

    def test_vercel_prod_blocked(self):
        policy = {
            "name": "no-deploy",
            "type": "command_contains",
            "tool": "Bash",
            "patterns": ["vercel deploy", "vercel --prod"],
            "message": "No production deploy",
        }
        result = evaluate_policy(policy, "Bash", {"command": "vercel --prod"}, "cto")
        assert result is not None

    def test_vercel_dev_allowed(self):
        policy = {
            "name": "no-deploy",
            "type": "command_contains",
            "tool": "Bash",
            "patterns": ["vercel deploy", "vercel --prod"],
            "message": "No production deploy",
        }
        result = evaluate_policy(policy, "Bash", {"command": "vercel dev"}, "cto")
        assert result is None

    def test_destructive_sql_blocked(self):
        policy = {
            "name": "no-sql",
            "type": "command_contains",
            "tool": "Bash",
            "patterns": ["DROP TABLE", "DROP DATABASE", "TRUNCATE", "DELETE FROM"],
            "case_sensitive": True,
            "message": "Destructive SQL",
        }
        result = evaluate_policy(
            policy, "Bash", {"command": "psql -c 'DROP TABLE users'"}, "cto"
        )
        assert result is not None
        assert "Destructive SQL" in result

    def test_lowercase_drop_allowed(self):
        """Case-sensitive: 'drop table' should not match 'DROP TABLE'."""
        policy = {
            "name": "no-sql",
            "type": "command_contains",
            "tool": "Bash",
            "patterns": ["DROP TABLE"],
            "case_sensitive": True,
            "message": "Destructive SQL",
        }
        result = evaluate_policy(
            policy, "Bash", {"command": "echo 'drop table'"}, "cto"
        )
        assert result is None

    def test_patterns_all_requires_both(self):
        """patterns_all: ALL groups must match."""
        policy = {
            "name": "git-workspace",
            "type": "command_contains",
            "tool": "Bash",
            "patterns_all": ["git commit|git push|git add", "/workspace/"],
            "message": "Git blocked",
        }
        # Has git commit but not /workspace/ — should NOT block
        result = evaluate_policy(
            policy, "Bash", {"command": "git commit -m 'fix'"}, "cpo"
        )
        assert result is None

        # Has both — should block
        result = evaluate_policy(
            policy,
            "Bash",
            {"command": "cd /workspace/product && git commit -m 'fix'"},
            "cpo",
        )
        assert result is not None

    def test_patterns_all_or_within_group(self):
        """patterns_all: | within a group means OR."""
        policy = {
            "name": "git-workspace",
            "type": "command_contains",
            "tool": "Bash",
            "patterns_all": ["git commit|git push|git add", "/workspace/"],
            "message": "Git blocked",
        }
        # git push instead of git commit — still matches first group
        result = evaluate_policy(
            policy,
            "Bash",
            {"command": "cd /workspace/product && git push"},
            "cpo",
        )
        assert result is not None

    def test_wrong_tool_not_blocked(self):
        """Policy with tool: Bash should not fire for Edit tool."""
        policy = {
            "name": "no-deploy",
            "type": "command_contains",
            "tool": "Bash",
            "patterns": ["vercel deploy"],
            "message": "No deploy",
        }
        result = evaluate_policy(
            policy, "Edit", {"file_path": "/tmp/vercel deploy"}, "cto"
        )
        assert result is None


# ===================================================================
# 5. PATH BLOCK POLICIES
# ===================================================================

class TestPathBlock:
    """Test path_block policy type."""

    def test_constitution_readonly(self):
        policy = {
            "name": "constitution-readonly",
            "type": "path_block",
            "tools": ["Edit", "Write"],
            "path_patterns": ["*/constitution/*"],
            "message": "Constitution is read-only",
        }
        result = evaluate_policy(
            policy,
            "Edit",
            {"file_path": "/opt/founders-cabinet/constitution/CONSTITUTION.md"},
            "cto",
        )
        assert result is not None
        assert "read-only" in result

    def test_constitution_read_allowed(self):
        """Reading constitution with Read tool should be allowed."""
        policy = {
            "name": "constitution-readonly",
            "type": "path_block",
            "tools": ["Edit", "Write"],
            "path_patterns": ["*/constitution/*"],
            "message": "Constitution is read-only",
        }
        result = evaluate_policy(
            policy,
            "Read",
            {"file_path": "/opt/founders-cabinet/constitution/CONSTITUTION.md"},
            "cto",
        )
        assert result is None

    def test_env_file_blocked(self):
        policy = {
            "name": "env-readonly",
            "type": "path_block",
            "tools": ["Edit", "Write"],
            "path_patterns": ["*.env", "*.env.*"],
            "message": "Env files blocked",
        }
        result = evaluate_policy(
            policy,
            "Write",
            {"file_path": "/opt/founders-cabinet/cabinet/.env"},
            "cto",
        )
        assert result is not None

    def test_env_local_blocked(self):
        policy = {
            "name": "env-readonly",
            "type": "path_block",
            "tools": ["Edit", "Write"],
            "path_patterns": ["*.env", "*.env.*"],
            "message": "Env files blocked",
        }
        result = evaluate_policy(
            policy,
            "Edit",
            {"file_path": "/opt/founders-cabinet/cabinet/.env.local"},
            "cto",
        )
        assert result is not None

    def test_non_env_file_allowed(self):
        policy = {
            "name": "env-readonly",
            "type": "path_block",
            "tools": ["Edit", "Write"],
            "path_patterns": ["*.env", "*.env.*"],
            "message": "Env files blocked",
        }
        result = evaluate_policy(
            policy,
            "Edit",
            {"file_path": "/opt/founders-cabinet/cabinet/config.yml"},
            "cto",
        )
        assert result is None

    def test_infrastructure_blocked_for_cto(self):
        policy = {
            "name": "infrastructure",
            "type": "path_block",
            "tools": ["Edit", "Write"],
            "path_patterns": ["*cabinet/docker-compose*", "*Dockerfile*"],
            "exempt_officers": ["cos"],
            "message": "Infrastructure blocked",
        }
        result = evaluate_policy(
            policy,
            "Edit",
            {"file_path": "/opt/founders-cabinet/cabinet/docker-compose.yml"},
            "cto",
        )
        assert result is not None

    def test_infrastructure_allowed_for_cos(self):
        """CoS is exempt from infrastructure block."""
        policy = {
            "name": "infrastructure",
            "type": "path_block",
            "tools": ["Edit", "Write"],
            "path_patterns": ["*cabinet/docker-compose*", "*Dockerfile*"],
            "exempt_officers": ["cos"],
            "message": "Infrastructure blocked",
        }
        result = evaluate_policy(
            policy,
            "Edit",
            {"file_path": "/opt/founders-cabinet/cabinet/docker-compose.yml"},
            "cos",
        )
        assert result is None

    def test_dockerfile_blocked(self):
        policy = {
            "name": "infrastructure",
            "type": "path_block",
            "tools": ["Edit", "Write"],
            "path_patterns": ["*cabinet/docker-compose*", "*Dockerfile*"],
            "exempt_officers": ["cos"],
            "message": "Infrastructure blocked",
        }
        result = evaluate_policy(
            policy,
            "Write",
            {"file_path": "/opt/founders-cabinet/Dockerfile"},
            "cpo",
        )
        assert result is not None


# ===================================================================
# 6. CODEBASE OWNERSHIP (path_block + bash_write_to_path)
# ===================================================================

class TestCodebaseOwnership:
    """Test codebase ownership policies — CTO exemption."""

    CODEBASE_POLICY = {
        "name": "codebase-ownership",
        "type": "path_block",
        "tools": ["Edit", "Write"],
        "path_patterns": ["/workspace/*/"],
        "exempt_officers": ["cto"],
        "message": "Only CTO can modify product code",
    }

    def test_cpo_blocked_from_product(self):
        result = evaluate_policy(
            self.CODEBASE_POLICY,
            "Edit",
            {"file_path": "/workspace/product/src/app.tsx"},
            "cpo",
        )
        assert result is not None
        assert "CTO" in result

    def test_cto_allowed_product(self):
        result = evaluate_policy(
            self.CODEBASE_POLICY,
            "Edit",
            {"file_path": "/workspace/product/src/app.tsx"},
            "cto",
        )
        assert result is None

    def test_cos_blocked_from_product(self):
        result = evaluate_policy(
            self.CODEBASE_POLICY,
            "Write",
            {"file_path": "/workspace/product/package.json"},
            "cos",
        )
        assert result is not None

    def test_non_workspace_allowed(self):
        result = evaluate_policy(
            self.CODEBASE_POLICY,
            "Edit",
            {"file_path": "/opt/founders-cabinet/shared/interfaces/foo.md"},
            "cpo",
        )
        assert result is None


class TestBashWriteToPath:
    """Test bash_write_to_path policy type — product codebase ownership."""

    BASH_WRITE_POLICY = {
        "name": "codebase-bash-write",
        "type": "bash_write_to_path",
        "path_pattern": "/workspace/[a-z0-9][a-z0-9-]*/",
        "exempt_officers": ["cto"],
        "message": "Only CTO can write via Bash",
    }

    def test_redirect_to_product(self):
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "echo hello > /workspace/product/out.txt"},
            "cpo",
        )
        assert result is not None

    def test_append_to_product(self):
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "echo hello >> /workspace/product/out.txt"},
            "cpo",
        )
        assert result is not None

    def test_sed_i_product(self):
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "sed -i 's/old/new/' /workspace/product/file.txt"},
            "cpo",
        )
        assert result is not None

    def test_tee_to_product(self):
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "echo hello | tee /workspace/product/out.txt"},
            "cpo",
        )
        assert result is not None

    def test_cp_to_product(self):
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "cp /tmp/file /workspace/product/file"},
            "cpo",
        )
        assert result is not None

    def test_mv_to_product(self):
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "mv /tmp/file /workspace/product/file"},
            "cpo",
        )
        assert result is not None

    def test_patch_product(self):
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "patch /workspace/product/file.c < fix.patch"},
            "cpo",
        )
        assert result is not None

    def test_perl_i_product(self):
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "perl -pi -e 's/old/new/' /workspace/product/file.txt"},
            "cpo",
        )
        assert result is not None

    def test_tar_extract_to_product(self):
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "tar -xf archive.tar -C /workspace/product/"},
            "cpo",
        )
        assert result is not None

    def test_cto_allowed(self):
        """CTO is exempt."""
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "echo hello > /workspace/product/out.txt"},
            "cto",
        )
        assert result is None

    def test_cat_product_allowed(self):
        """cat (read) from product should NOT be blocked."""
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "cat /workspace/product/file.txt"},
            "cpo",
        )
        assert result is None

    def test_grep_product_allowed(self):
        """grep (read) from product should NOT be blocked."""
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "grep pattern /workspace/product/file.txt"},
            "cpo",
        )
        assert result is None

    def test_ls_product_allowed(self):
        """ls product directory should NOT be blocked."""
        result = evaluate_policy(
            self.BASH_WRITE_POLICY,
            "Bash",
            {"command": "ls /workspace/product/src/"},
            "cpo",
        )
        assert result is None


# ===================================================================
# 7. TIER2 ISOLATION
# ===================================================================

class TestTier2Isolation:
    """Test tier2_isolation policy type."""

    TIER2_POLICY = {
        "name": "tier2-isolation",
        "type": "tier2_isolation",
        "tools": ["Edit", "Write"],
        "base_path": "instance/memory/tier2/",
        "message": "Officers can only write to their own tier2 directory",
    }

    def test_cto_own_tier2_allowed(self):
        result = evaluate_policy(
            self.TIER2_POLICY,
            "Edit",
            {"file_path": "/opt/founders-cabinet/instance/memory/tier2/cto/notes.md"},
            "cto",
        )
        assert result is None

    def test_cto_other_tier2_blocked(self):
        result = evaluate_policy(
            self.TIER2_POLICY,
            "Edit",
            {"file_path": "/opt/founders-cabinet/instance/memory/tier2/cpo/notes.md"},
            "cto",
        )
        assert result is not None
        assert "tier2" in result.lower()

    def test_cos_own_tier2_allowed(self):
        result = evaluate_policy(
            self.TIER2_POLICY,
            "Write",
            {"file_path": "/opt/founders-cabinet/instance/memory/tier2/cos/working.md"},
            "cos",
        )
        assert result is None

    def test_non_tier2_path_allowed(self):
        """Paths outside tier2 are not subject to this policy."""
        result = evaluate_policy(
            self.TIER2_POLICY,
            "Edit",
            {"file_path": "/opt/founders-cabinet/shared/interfaces/foo.md"},
            "cto",
        )
        assert result is None


# ===================================================================
# 8. POLICY LOADING
# ===================================================================

class TestPolicyLoading:
    """Test load_policies with framework + preset layering."""

    def test_loads_from_framework_and_preset(self):
        """Policies from both framework/ and presets/ directories load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create framework policies
            fw_dir = Path(tmpdir) / "framework" / "policies"
            fw_dir.mkdir(parents=True)
            (fw_dir / "base.yml").write_text(
                "version: 1\npolicies:\n"
                "  - name: fw-policy\n"
                "    type: binary_block\n"
                '    binaries: [sudo]\n'
                '    message: "blocked"\n'
            )

            # Create preset policies
            preset_dir = Path(tmpdir) / "presets" / "work" / "policies"
            preset_dir.mkdir(parents=True)
            (preset_dir / "work.yml").write_text(
                "version: 1\npolicies:\n"
                "  - name: preset-policy\n"
                "    type: binary_block\n"
                '    binaries: [docker]\n'
                '    message: "blocked"\n'
            )

            # Create active-preset file
            instance_dir = Path(tmpdir) / "instance" / "config"
            instance_dir.mkdir(parents=True)
            (instance_dir / "active-preset").write_text("work")

            policies = load_policies(tmpdir)
            names = {p["name"] for p in policies}
            assert "fw-policy" in names
            assert "preset-policy" in names

    def test_preset_overrides_framework(self):
        """A preset policy with the same name overrides the framework one."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fw_dir = Path(tmpdir) / "framework" / "policies"
            fw_dir.mkdir(parents=True)
            (fw_dir / "base.yml").write_text(
                "version: 1\npolicies:\n"
                "  - name: shared-name\n"
                "    type: binary_block\n"
                '    binaries: [sudo]\n'
                '    message: "framework version"\n'
            )

            preset_dir = Path(tmpdir) / "presets" / "work" / "policies"
            preset_dir.mkdir(parents=True)
            (preset_dir / "override.yml").write_text(
                "version: 1\npolicies:\n"
                "  - name: shared-name\n"
                "    type: binary_block\n"
                '    binaries: [docker]\n'
                '    message: "preset version"\n'
            )

            instance_dir = Path(tmpdir) / "instance" / "config"
            instance_dir.mkdir(parents=True)
            (instance_dir / "active-preset").write_text("work")

            policies = load_policies(tmpdir)
            shared = [p for p in policies if p["name"] == "shared-name"]
            assert len(shared) == 1
            assert shared[0]["message"] == "preset version"
            assert shared[0]["binaries"] == ["docker"]

    def test_instance_overrides_preset(self):
        """Instance-level policies override preset ones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fw_dir = Path(tmpdir) / "framework" / "policies"
            fw_dir.mkdir(parents=True)
            (fw_dir / "base.yml").write_text(
                "version: 1\npolicies:\n"
                "  - name: my-policy\n"
                "    type: binary_block\n"
                '    binaries: [sudo]\n'
                '    message: "fw"\n'
            )

            instance_dir = Path(tmpdir) / "instance" / "config"
            instance_dir.mkdir(parents=True)
            (instance_dir / "active-preset").write_text("work")

            policy_dir = instance_dir / "policies"
            policy_dir.mkdir()
            (policy_dir / "override.yml").write_text(
                "version: 1\npolicies:\n"
                "  - name: my-policy\n"
                "    type: binary_block\n"
                '    binaries: [halt]\n'
                '    message: "instance"\n'
            )

            policies = load_policies(tmpdir)
            my = [p for p in policies if p["name"] == "my-policy"]
            assert len(my) == 1
            assert my[0]["message"] == "instance"

    def test_malformed_yaml_skipped(self):
        """Malformed YAML files are skipped without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fw_dir = Path(tmpdir) / "framework" / "policies"
            fw_dir.mkdir(parents=True)
            (fw_dir / "bad.yml").write_text("this is not: valid: yaml: [[[[")
            (fw_dir / "good.yml").write_text(
                "version: 1\npolicies:\n"
                "  - name: good-policy\n"
                "    type: binary_block\n"
                '    binaries: [sudo]\n'
                '    message: "ok"\n'
            )

            instance_dir = Path(tmpdir) / "instance" / "config"
            instance_dir.mkdir(parents=True)
            (instance_dir / "active-preset").write_text("work")

            policies = load_policies(tmpdir)
            # The good policy should load despite the bad file
            assert any(p["name"] == "good-policy" for p in policies)

    def test_empty_dir_returns_empty(self):
        """No policy files at all returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            instance_dir = Path(tmpdir) / "instance" / "config"
            instance_dir.mkdir(parents=True)
            (instance_dir / "active-preset").write_text("work")

            policies = load_policies(tmpdir)
            assert policies == []


# ===================================================================
# 9. OFFICER EXEMPTIONS
# ===================================================================

class TestOfficerExemptions:
    """Test that exempt_officers correctly bypasses policies."""

    def test_cto_exempt_from_codebase_block(self):
        policy = {
            "name": "codebase",
            "type": "path_block",
            "tools": ["Edit"],
            "path_patterns": ["/workspace/*/"],
            "exempt_officers": ["cto"],
            "message": "Blocked",
        }
        assert evaluate_policy(
            policy, "Edit", {"file_path": "/workspace/product/app.ts"}, "cto"
        ) is None
        assert evaluate_policy(
            policy, "Edit", {"file_path": "/workspace/product/app.ts"}, "cpo"
        ) is not None

    def test_cos_exempt_from_infra_block(self):
        policy = {
            "name": "infra",
            "type": "path_block",
            "tools": ["Edit", "Write"],
            "path_patterns": ["*Dockerfile*"],
            "exempt_officers": ["cos"],
            "message": "Blocked",
        }
        assert evaluate_policy(
            policy, "Edit", {"file_path": "/opt/Dockerfile"}, "cos"
        ) is None
        assert evaluate_policy(
            policy, "Edit", {"file_path": "/opt/Dockerfile"}, "cto"
        ) is not None

    def test_exempt_from_command_contains(self):
        policy = {
            "name": "git-workspace",
            "type": "command_contains",
            "tool": "Bash",
            "patterns_all": ["git push", "/workspace/"],
            "exempt_officers": ["cto"],
            "message": "Blocked",
        }
        assert evaluate_policy(
            policy,
            "Bash",
            {"command": "cd /workspace/product && git push"},
            "cto",
        ) is None
        assert evaluate_policy(
            policy,
            "Bash",
            {"command": "cd /workspace/product && git push"},
            "cpo",
        ) is not None

    def test_exempt_from_bash_write(self):
        policy = {
            "name": "bash-write",
            "type": "bash_write_to_path",
            "path_pattern": "/workspace/[a-z0-9][a-z0-9-]*/",
            "exempt_officers": ["cto"],
            "message": "Blocked",
        }
        assert evaluate_policy(
            policy,
            "Bash",
            {"command": "echo x > /workspace/product/f"},
            "cto",
        ) is None
        assert evaluate_policy(
            policy,
            "Bash",
            {"command": "echo x > /workspace/product/f"},
            "cos",
        ) is not None


# ===================================================================
# 10. PATH MATCHING HELPER
# ===================================================================

class TestPathMatching:
    """Test the _path_matches_pattern helper."""

    def test_glob_star_extension(self):
        assert _path_matches_pattern("/path/to/.env", "*.env")

    def test_glob_star_extension_with_suffix(self):
        assert _path_matches_pattern("/path/to/.env.local", "*.env.*")

    def test_glob_directory_wildcard(self):
        assert _path_matches_pattern(
            "/opt/founders-cabinet/constitution/CONSTITUTION.md",
            "*/constitution/*",
        )

    def test_glob_prefix_wildcard(self):
        assert _path_matches_pattern(
            "/opt/founders-cabinet/cabinet/docker-compose.yml",
            "*cabinet/docker-compose*",
        )

    def test_directory_pattern_with_trailing_slash(self):
        assert _path_matches_pattern(
            "/workspace/product/src/app.ts",
            "/workspace/*/",
        )

    def test_no_match(self):
        assert not _path_matches_pattern(
            "/opt/founders-cabinet/shared/foo.md",
            "*/constitution/*",
        )


# ===================================================================
# 11. QUOTE/ESCAPE STRIPPING
# ===================================================================

class TestStripQuotesAndEscapes:
    """Test the _strip_quotes_and_escapes helper."""

    def test_double_quoted(self):
        assert _strip_quotes_and_escapes('"sudo"') == "sudo"

    def test_single_quoted(self):
        assert _strip_quotes_and_escapes("'sudo'") == "sudo"

    def test_splice_middle(self):
        assert _strip_quotes_and_escapes('s"udo"') == "sudo"

    def test_double_splice(self):
        assert _strip_quotes_and_escapes('"su""do"') == "sudo"

    def test_backslash_escape(self):
        assert _strip_quotes_and_escapes("\\sudo") == "sudo"

    def test_ansi_c_quote(self):
        assert _strip_quotes_and_escapes("$'sudo'") == "sudo"

    def test_bare_word(self):
        assert _strip_quotes_and_escapes("sudo") == "sudo"


# ===================================================================
# 12. MAIN ENTRY POINT (integration-style)
# ===================================================================

class TestMainEntryPoint:
    """Test the main() function end-to-end via in-process invocation."""

    def test_allow_safe_command(self):
        """Safe command exits 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fw_dir = Path(tmpdir) / "framework" / "policies"
            fw_dir.mkdir(parents=True)
            (fw_dir / "base.yml").write_text(
                "version: 1\npolicies:\n"
                "  - name: no-sudo\n"
                "    type: binary_block\n"
                '    binaries: [sudo]\n'
                '    message: "blocked"\n'
            )
            instance_dir = Path(tmpdir) / "instance" / "config"
            instance_dir.mkdir(parents=True)
            (instance_dir / "active-preset").write_text("work")

            input_json = json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": "ls -la"},
            })

            from io import StringIO
            from policy_engine import main

            with patch.dict(os.environ, {"CABINET_ROOT": tmpdir, "OFFICER": "cto"}):
                with patch("sys.stdin", StringIO(input_json)):
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    assert exc_info.value.code == 0

    def test_block_sudo_command(self):
        """Sudo command exits 2 with message on stderr."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fw_dir = Path(tmpdir) / "framework" / "policies"
            fw_dir.mkdir(parents=True)
            (fw_dir / "base.yml").write_text(
                "version: 1\npolicies:\n"
                "  - name: no-sudo\n"
                "    type: binary_block\n"
                '    binaries: [sudo]\n'
                '    message: "System-level command not permitted"\n'
            )
            instance_dir = Path(tmpdir) / "instance" / "config"
            instance_dir.mkdir(parents=True)
            (instance_dir / "active-preset").write_text("work")

            input_json = json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": "sudo ls"},
            })

            from io import StringIO
            from policy_engine import main

            stderr_capture = StringIO()
            with patch.dict(os.environ, {"CABINET_ROOT": tmpdir, "OFFICER": "cto"}):
                with patch("sys.stdin", StringIO(input_json)):
                    with patch("sys.stderr", stderr_capture):
                        with pytest.raises(SystemExit) as exc_info:
                            main()
                        assert exc_info.value.code == 2
            assert "System-level command not permitted" in stderr_capture.getvalue()

    def test_malformed_json_allows(self):
        """Malformed JSON input exits 0 (fail-open)."""
        from io import StringIO
        from policy_engine import main

        with patch.dict(os.environ, {"CABINET_ROOT": "/nonexistent"}):
            with patch("sys.stdin", StringIO("not json at all")):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0


# ===================================================================
# 13. EDGE CASES
# ===================================================================

class TestEdgeCases:
    """Edge cases and regression guards."""

    BLOCK_POLICY = {
        "name": "test-block",
        "type": "binary_block",
        "binaries": ["sudo", "docker", "systemctl", "shutdown", "reboot", "halt"],
        "message": "blocked",
    }

    def test_empty_command(self):
        result = evaluate_policy(
            self.BLOCK_POLICY, "Bash", {"command": ""}, "cto"
        )
        assert result is None

    def test_whitespace_only_command(self):
        result = evaluate_policy(
            self.BLOCK_POLICY, "Bash", {"command": "   "}, "cto"
        )
        assert result is None

    def test_non_bash_tool_ignored(self):
        result = evaluate_policy(
            self.BLOCK_POLICY, "Read", {"file_path": "/usr/bin/sudo"}, "cto"
        )
        assert result is None

    def test_missing_command_key(self):
        result = evaluate_policy(
            self.BLOCK_POLICY, "Bash", {}, "cto"
        )
        assert result is None

    def test_unknown_officer_not_exempt(self):
        policy = {
            "name": "test",
            "type": "binary_block",
            "binaries": ["sudo"],
            "exempt_officers": ["cto"],
            "message": "blocked",
        }
        result = evaluate_policy(
            policy, "Bash", {"command": "sudo ls"}, "unknown"
        )
        assert result is not None

    def test_file_path_via_path_key(self):
        """Some tools use 'path' instead of 'file_path'."""
        policy = {
            "name": "test",
            "type": "path_block",
            "tools": ["Edit"],
            "path_patterns": ["*.env"],
            "message": "blocked",
        }
        result = evaluate_policy(
            policy, "Edit", {"path": "/opt/.env"}, "cto"
        )
        assert result is not None

    def test_destructive_rm_policy_type(self):
        """Explicit destructive_rm policy type works."""
        policy = {
            "name": "no-rm",
            "type": "destructive_rm",
            "message": "Destructive rm",
        }
        assert evaluate_policy(
            policy, "Bash", {"command": "rm -rf /"}, "cto"
        ) is not None
        assert evaluate_policy(
            policy, "Bash", {"command": "rm file.txt"}, "cto"
        ) is None

    def test_multiple_binaries_in_compound(self):
        """Compound command with multiple blocked binaries."""
        binaries = extract_invoked_binaries("sudo ls; docker run; systemctl restart")
        assert "sudo" in binaries
        assert "docker" in binaries
        assert "systemctl" in binaries


# ===================================================================
# 6. AUTHORITY MATRIX POLICY TYPE [T6] — fail-safe, shadow-capable
# ===================================================================
# Design: docs/authority-matrix-design-2026-06-19.md §1 Component 2 + §3
# read_cell_state + the fail-safe inventory. The authority_matrix eval turns
# matrix data into a per-action verdict and returns a block message (force
# propose-only / gated) or None (allow). In A0 the confidence read is STUBBED
# to "unmeasured" (F2 graduation.py is not built), so EVERY cell resolves to a
# block: non-ceiling rows -> propose_only, ceiling rows -> always_gated. The
# gate NEVER returns auto/None in A0. SHADOW-ONLY: this adds no live exit-2.

from policy_engine import (  # noqa: E402
    _eval_authority_matrix,
    risk_of,
    resolve_verdict,
    read_cell_state,
)

# Import the validated, shipped matrix floor so tests run against the REAL
# production data (the loader/validator is matrix.py, shipped in T5).
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_real_matrix_policy() -> dict:
    """Return the single authority_matrix policy from the shipped framework
    floor (validated by matrix.py on load)."""
    from framework.authority import matrix as M  # noqa: E402

    return M.matrix_policy(M.load_matrix())


def _real_hard_ceiling_members() -> set:
    """The six HARD_CEILING_TOUCHES members (the code-level backstop)."""
    from framework.learning.capability_gaps import HARD_CEILING_TOUCHES  # noqa: E402

    return set(HARD_CEILING_TOUCHES)


# Mapping from a hard-ceiling risk_class -> a tool call that classify_action
# positively resolves into that risk_class. Used to prove each ceiling member
# gates end-to-end through classify_action -> risk_of -> hard-ceiling.
_CEILING_PROBES = {
    "external_comms": (
        "mcp__brain__queue_draft",
        {"recipient": "outsider@gmail.com", "body": "hi", "channel": "teams"},
    ),
    "deploy_prod": ("Bash", {"command": "git push origin main"}),
    "spend": ("Bash", {"command": "stripe charge --amount 5000"}),
    "secrets": ("Write", {"file_path": "/workspace/product/.env", "content": "X=1"}),
    "network_write": (
        "mcp__some__create_post",
        {},
    ),
    "credentials_grant": ("Bash", {"command": "oauth grant token"}),
}


class TestRiskOf:
    """enum action_type -> risk_class resolution."""

    def test_known_action_type_resolves(self):
        pol = _load_real_matrix_policy()
        assert risk_of("local_edit", pol["risk_classes"]) == "reversible"
        assert risk_of("internal_message", pol["risk_classes"]) == "internal_comms"
        assert risk_of("git_push_main", pol["risk_classes"]) == "deploy_prod"
        assert risk_of("env_write", pol["risk_classes"]) == "secrets"
        assert risk_of("mcp_post", pol["risk_classes"]) == "network_write"
        assert risk_of("oauth_grant", pol["risk_classes"]) == "credentials_grant"

    def test_unknown_action_type_returns_none(self):
        pol = _load_real_matrix_policy()
        assert risk_of("ambiguous", pol["risk_classes"]) is None
        assert risk_of("not_a_real_action_type", pol["risk_classes"]) is None

    def test_malformed_risk_classes_returns_none(self):
        # Defensive: a non-dict / missing structure must not raise — fail-safe.
        assert risk_of("local_edit", {}) is None
        assert risk_of("local_edit", None) is None  # type: ignore[arg-type]
        assert risk_of("local_edit", {"reversible": {}}) is None
        assert risk_of("local_edit", {"reversible": {"action_types": "nope"}}) is None


class TestResolveVerdict:
    """verdict-table resolution incl. the '*' wildcard rows."""

    def test_explicit_state_resolution(self):
        pol = _load_real_matrix_policy()
        v = pol["verdicts"]
        # TRUST-INVERSION (germline batch 2026-07-04, earn-demotion ruling):
        # the reversible row is act_with_undo at every non-demote state —
        # trust granted day-one, lost only on demotion evidence. The old
        # earn-up pins (propose_only@unmeasured, auto@graduated) are the
        # exact posture matrix._validate_act_first_floor now hard-REJECTS.
        assert resolve_verdict(v, "reversible", "graduated") == "act_with_undo"
        assert resolve_verdict(v, "reversible", "unmeasured") == "act_with_undo"
        assert resolve_verdict(v, "reversible", "eligible") == "act_with_undo"
        assert resolve_verdict(v, "reversible", "demote") == "propose_only"
        assert resolve_verdict(v, "internal_comms", "graduated") == "auto_with_veto_window"
        assert resolve_verdict(v, "internal_comms", "unmeasured") == "propose_only"
        assert resolve_verdict(v, "deploy_nonprod", "graduated") == "classifier"
        assert resolve_verdict(v, "deploy_nonprod", "unmeasured") == "propose_only"

    def test_wildcard_row_resolution(self):
        pol = _load_real_matrix_policy()
        v = pol["verdicts"]
        # Hard-ceiling rows are {"*": always_gated} — every state hits the wildcard.
        for state in ("unmeasured", "propose_only", "eligible", "graduated", "demote"):
            assert resolve_verdict(v, "external_comms", state) == "always_gated"
            assert resolve_verdict(v, "deploy_prod", state) == "always_gated"
            assert resolve_verdict(v, "spend", state) == "always_gated"
            assert resolve_verdict(v, "secrets", state) == "always_gated"
            assert resolve_verdict(v, "network_write", state) == "always_gated"
            assert resolve_verdict(v, "credentials_grant", state) == "always_gated"

    def test_missing_cell_fails_safe_to_propose_only(self):
        # An absent risk_class or absent state must NOT raise and must NOT
        # resolve to auto — fail-safe to propose_only.
        v = {"reversible": {"graduated": "auto"}}
        assert resolve_verdict(v, "reversible", "unmeasured") == "propose_only"
        assert resolve_verdict(v, "nonexistent", "graduated") == "propose_only"
        assert resolve_verdict({}, "reversible", "graduated") == "propose_only"
        assert resolve_verdict(None, "reversible", "graduated") == "propose_only"  # type: ignore[arg-type]


class TestReadCellState:
    """read_cell_state is STUBBED to 'unmeasured' in A0 (F2 not built)."""

    def test_always_unmeasured(self):
        assert read_cell_state("cto", "polads", "local_edit") == "unmeasured"
        assert read_cell_state("cos", None, "internal_message") == "unmeasured"
        assert read_cell_state("cro", "stephie", "git_push_nonmain") == "unmeasured"

    def test_unmeasured_even_with_weird_inputs(self):
        # Fail-safe: any input still reads unmeasured (no graduation source yet).
        assert read_cell_state("", "", "") == "unmeasured"
        assert read_cell_state(None, None, None) == "unmeasured"  # type: ignore[arg-type]


class TestReadCellStateFailClosed:
    """MF-1 (checkpoint review lane-germline-0705-cp1, 2026-07-05): the live
    (un-stubbed) read_cell_state resolves its two failure directions
    DIFFERENTLY post-act-first-widening. No-evidence stays trust-first
    "unmeasured" (act_with_undo day-one for reversible classes), but a read
    ERROR or an out-of-vocabulary state must fail CLOSED to "demote"
    (propose_only across every class): unmeasured now means ALLOW, so
    resolving a broken evidence plane to "unmeasured" would silently ERASE a
    demotion at exactly the enforcing gate. (TestReadCellState above predates
    the un-stub; its cells still legitimately read unmeasured because the
    fenced test ledger carries no rows for them.)"""

    @staticmethod
    def _graduation():
        from framework.fidelity import graduation  # the module read_cell_state
        return graduation                          # lazily imports at call time

    def test_evaluate_exception_fails_closed_to_demote(self):
        with patch.object(self._graduation(), "evaluate",
                          side_effect=RuntimeError("evidence plane broken")):
            assert read_cell_state("cos", "polads", "task_create") == "demote"

    def test_no_cell_rows_is_legit_unmeasured(self):
        # None = a cell with no evidence yet — the trust-first case, NOT an
        # error: a brand-new reversible cell is act_with_undo from day one.
        with patch.object(self._graduation(), "evaluate", return_value=None):
            assert read_cell_state("cos", "polads", "task_create") == "unmeasured"

    def test_out_of_vocab_state_fails_closed_to_demote(self):
        # An unknown state must never be trusted — it is a read failure, not a
        # new kind of permission.
        with patch.object(self._graduation(), "evaluate",
                          return_value={"state": "turbo-graduated"}):
            assert read_cell_state("cos", "polads", "task_create") == "demote"

    def test_known_states_pass_through_verbatim(self):
        # The whole _CELL_STATES vocabulary passes through untouched — the
        # fail-closed wrapper must not distort a real reading (incl. a real
        # demote, the brake this batch wired).
        for state in ("unmeasured", "propose_only", "eligible", "graduated",
                      "demote"):
            with patch.object(self._graduation(), "evaluate",
                              return_value={"state": state}):
                assert read_cell_state("cos", "polads", "task_create") == state

    def test_cell_key_composes_single_officer_prefix(self):
        # CANONICAL ACTOR-ID JOIN (germline 2026-07-04): the query composes
        # "officer:" + the BARE role. Pin the join key — a pre-prefixed id
        # double-composes to "officer:officer:cos" and silently severs
        # demotion evidence from the gate (the shipped severing bug this
        # batch fixed).
        seen = {}

        def spy(cell, **kw):
            seen["cell"] = cell
            return {"state": "graduated"}

        with patch.object(self._graduation(), "evaluate", new=spy):
            assert read_cell_state("cos", "polads", "task_create") == "graduated"
        assert seen["cell"] == ("officer:cos", "polads", "task_create")


class TestEvalAuthorityMatrix:
    """The eval end-to-end: verdict resolution + the fail-safe spine."""

    def test_reversible_unmeasured_acts_with_undo(self):
        """TRUST-INVERSION (germline batch 2026-07-04, supersedes the old
        test_reversible_unmeasured_proposes): a plain local edit -> reversible
        -> unmeasured -> act_with_undo -> ALLOW, because local_edit has a
        registered deterministic inverse (action_undo file_compare_restore)
        and the undo journal is reachable. Shadow-consumed until the
        Captain-gated enforcement flip — the gate verdict changes, live
        behavior does not (CABINET_AUTHORITY_ENFORCING still defaults 0)."""
        pol = _load_real_matrix_policy()
        with tempfile.TemporaryDirectory() as tmp:
            # hermetic journal-reachability: never depend on the machine's
            # real ~/Library undo dir (same override discipline as _undo_dir).
            with patch.dict(os.environ, {"CABINET_UNDO_DIR": tmp}):
                result = _eval_authority_matrix(
                    pol, "Edit", {"file_path": "/workspace/product/src/foo.ts"}, "cto"
                )
        assert result is None  # allow — act_with_undo with a viable undo plane

    def test_reversible_act_with_undo_falls_safe_without_journal(self):
        """The Corridor-confirmed fail-safe: same reversible cell, but the
        undo journal path is UNREACHABLE — CABINET_UNDO_DIR points below a
        plain FILE, so _act_with_undo_gap's walk-up lands on a non-dir
        ancestor -> "undo journal dir unreachable" -> the allow branch must
        fall through to propose-only naming the gap (never allow)."""
        pol = _load_real_matrix_policy()
        with tempfile.TemporaryDirectory() as tmp:
            blocker = os.path.join(tmp, "not-a-dir")
            with open(blocker, "w") as fh:
                fh.write("x")
            with patch.dict(os.environ,
                            {"CABINET_UNDO_DIR": os.path.join(blocker, "undo")}):
                result = _eval_authority_matrix(
                    pol, "Edit", {"file_path": "/workspace/product/src/foo.ts"}, "cto"
                )
        assert result is not None
        assert "PROPOSE-ONLY" in result
        assert "act_with_undo" in result  # the gap-naming message

    def test_internal_comms_unmeasured_proposes(self):
        pol = _load_real_matrix_policy()
        result = _eval_authority_matrix(
            pol,
            "mcp__brain__queue_draft",
            {"recipient": "sean@stepnetwork.dk", "body": "hi", "channel": "teams"},
            "cos",
        )
        # internal_comms graduated -> auto_with_veto_window, but stub state is
        # unmeasured -> propose_only. Must NOT auto / veto-enqueue in A0.
        assert result is not None
        assert "PROPOSE-ONLY" in result

    def test_deploy_nonprod_unmeasured_proposes(self):
        pol = _load_real_matrix_policy()
        result = _eval_authority_matrix(
            pol, "Bash", {"command": "git push origin feature/x"}, "cto"
        )
        # deploy_nonprod graduated/eligible -> classifier; unmeasured ->
        # propose_only. Never reaches the classifier branch in A0.
        assert result is not None
        assert "PROPOSE-ONLY" in result

    def test_all_six_hard_ceiling_members_gate(self):
        """Every one of the six HARD_CEILING_TOUCHES members gates regardless
        of confidence — the hard-ceiling short-circuit [FIX-7]."""
        pol = _load_real_matrix_policy()
        ceiling_classes = set(pol["hard_ceiling"])
        # Sanity: the matrix's hard_ceiling covers all six frozenset members
        # (by the ceiling_frozenset_map; the risk_classes themselves are 6).
        assert len(ceiling_classes) == 6
        for risk_class, (tool_name, tool_input) in _CEILING_PROBES.items():
            assert risk_class in ceiling_classes, risk_class
            result = _eval_authority_matrix(pol, tool_name, tool_input, "cto")
            assert result is not None, f"{risk_class} must gate"
            assert "GATED" in result, f"{risk_class}: {result}"
            assert risk_class in result, f"{risk_class}: {result}"

    def test_external_comms_directs_to_queue_draft(self):
        pol = _load_real_matrix_policy()
        result = _eval_authority_matrix(
            pol,
            "mcp__brain__queue_draft",
            {"recipient": "outsider@example.com", "body": "x", "channel": "email"},
            "cos",
        )
        assert result is not None
        assert "GATED" in result
        assert "external_comms" in result
        assert "queue_draft" in result

    def test_unknown_action_type_proposes(self):
        pol = _load_real_matrix_policy()
        # An ambiguous tool call -> classify_action returns AMBIGUOUS ->
        # risk_of returns None -> fail-safe propose_only.
        result = _eval_authority_matrix(
            pol, "SomeRandomTool", {"weird": "payload"}, "cto"
        )
        assert result is not None
        assert "PROPOSE-ONLY" in result

    def test_gate_allows_only_act_with_undo_cells_at_unmeasured(self):
        """The fail-closed spine, POST trust-inversion (germline batch
        2026-07-04 — supersedes the old test_gate_never_returns_auto_in_a0):
        across a broad sample of action types at unmeasured confidence, the
        ONLY allows are cells the Captain-ratified matrix maps to
        act_with_undo AND whose undo plane is mechanically viable (registered
        inverse + reachable journal). Everything else — hard ceilings,
        earn-up rows (internal_comms, deploy_nonprod), and the ambiguous
        backstop — still blocks. `auto` remains unreachable at unmeasured."""
        pol = _load_real_matrix_policy()
        # (tool, input, allow_expected) — allow_expected True ONLY for
        # act_with_undo classes: local_edit/task_status_move/... (reversible)
        # and board_status/task_create (pm_write). Everything Bash that
        # classifies local_edit (plain `ls -la`) rides the same row.
        probes = [
            ("Edit", {"file_path": "/workspace/product/a.ts"}, True),
            ("Write", {"file_path": "/workspace/product/b.ts", "content": "x"}, True),
            ("Read", {"file_path": "/workspace/product/c.ts"}, True),
            ("Bash", {"command": "ls -la"}, True),
            ("Bash", {"command": "git push origin feature/x"}, False),
            ("Bash", {"command": "git push origin main"}, False),
            ("Bash", {"command": "vercel deploy"}, False),
            ("Bash", {"command": "vercel --prod"}, False),
            ("Bash", {"command": "stripe charge --amount 100"}, False),
            ("Bash", {"command": "cat /workspace/product/.env"}, False),
            ("Bash", {"command": "oauth grant token"}, False),
            (
                "mcp__brain__queue_draft",
                {"recipient": "sean@stepnetwork.dk", "channel": "teams"},
                False,
            ),
            (
                "mcp__brain__queue_draft",
                {"recipient": "out@example.com", "channel": "email"},
                False,
            ),
            ("mcp__monday_com__change_item_column_values", {}, True),
            ("mcp__some__create_post", {}, False),
            ("SomeRandomTool", {"x": 1}, False),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"CABINET_UNDO_DIR": tmp}):
                for tool_name, tool_input, allow_expected in probes:
                    result = _eval_authority_matrix(pol, tool_name, tool_input, "cto")
                    if allow_expected:
                        assert result is None, (
                            f"act_with_undo cell blocked: {tool_name} {tool_input} "
                            f"-> {result}"
                        )
                    else:
                        assert result is not None, (
                            f"gate returned allow for {tool_name} {tool_input} — "
                            f"fail-closed invariant violated (only act_with_undo "
                            f"cells may allow at unmeasured)"
                        )

    def test_malformed_policy_fails_safe(self):
        """A malformed/empty policy dict must NOT raise and must NOT allow —
        defensive .get() with fail-safe defaults."""
        # Missing risk_classes/verdicts/hard_ceiling entirely.
        result = _eval_authority_matrix(
            {}, "Edit", {"file_path": "/x.ts"}, "cto"
        )
        assert result is not None
        assert "PROPOSE-ONLY" in result

    def test_dispatch_via_evaluate_policy(self):
        """evaluate_policy() routes authority_matrix to the eval. The
        propose-only probe is deploy_nonprod (earn-up kept, NATE-DECISION
        2026-07-04) — the old Edit probe now rides the act_with_undo allow
        branch (trust-inversion) and no longer blocks."""
        pol = _load_real_matrix_policy()
        # An earn-up action at unmeasured -> propose_only (block message).
        result = evaluate_policy(
            pol, "Bash", {"command": "git push origin feature/x"}, "cto"
        )
        assert result is not None
        assert "PROPOSE-ONLY" in result
        # A hard-ceiling action -> gated.
        result = evaluate_policy(
            pol, "Bash", {"command": "git push origin main"}, "cto"
        )
        assert result is not None
        assert "GATED" in result

    def test_exempt_officer_still_bypasses(self):
        """The shared exempt_officers gate in evaluate_policy applies to
        authority_matrix too (consistency with the other types)."""
        pol = dict(_load_real_matrix_policy())
        pol["exempt_officers"] = ["cto"]
        result = evaluate_policy(
            pol, "Bash", {"command": "git push origin main"}, "cto"
        )
        assert result is None  # exempt -> no policy decision

    def test_ceiling_coverage_matches_frozenset(self):
        """The matrix's hard-ceiling rows cover all six HARD_CEILING_TOUCHES
        members and each gates — ties the gate to the code-level backstop."""
        from framework.authority import matrix as M  # noqa: E402

        pol = _load_real_matrix_policy()
        covered = M.ceiling_members(pol)
        assert covered == _real_hard_ceiling_members()


class TestAuthorityMatrixNoLiveBlock:
    """A0 is SHADOW-ONLY: the eval is reachable as a library function and via
    evaluate_policy, but the live hook (pre-tool-use.sh) must NOT add a new
    exit-2 that blocks a real action on the authority verdict. This guards the
    'no live behavior change' invariant at the source-text level."""

    def test_pre_tool_use_has_no_authority_exit2(self):
        hook = (_REPO_ROOT / "cabinet" / "scripts" / "hooks" / "pre-tool-use.sh").read_text()
        # The hook may reference the enforcing flag in a comment/future stub,
        # but must NOT yet evaluate the authority_matrix verdict to exit 2.
        assert "_eval_authority_matrix" not in hook
        assert "evaluate_policy" not in hook

    def test_main_does_not_block_on_authority_matrix(self):
        """main() loading a real matrix floor must exit 0 on a reversible
        action — main() only enforces the LEGACY typed rules; the authority
        verdict is shadow-only (consumed by policy-shadow.py in a later task),
        so authority_matrix policies are skipped by main()'s live loop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fw_dir = Path(tmpdir) / "framework" / "policies"
            fw_dir.mkdir(parents=True)
            # Copy ONLY the authority matrix into the temp framework dir.
            real_matrix = (
                _REPO_ROOT / "framework" / "policies" / "authority-matrix.yml"
            ).read_text()
            (fw_dir / "authority-matrix.yml").write_text(real_matrix)
            instance_dir = Path(tmpdir) / "instance" / "config"
            instance_dir.mkdir(parents=True)
            (instance_dir / "active-preset").write_text("work")

            input_json = json.dumps({
                "tool_name": "Edit",
                "tool_input": {"file_path": "/workspace/product/a.ts"},
            })

            from io import StringIO
            from policy_engine import main

            with patch.dict(os.environ, {"CABINET_ROOT": tmpdir, "OFFICER": "cto"}):
                with patch("sys.stdin", StringIO(input_json)):
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    # A0 shadow-only: main() does NOT live-block on authority.
                    assert exc_info.value.code == 0

    def test_main_default_env_is_shadow(self):
        """With CABINET_AUTHORITY_ENFORCING UNSET (the default), main() must
        not live-block on a hard-ceiling authority action — the flag defaults
        to shadow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fw_dir = Path(tmpdir) / "framework" / "policies"
            fw_dir.mkdir(parents=True)
            real_matrix = (
                _REPO_ROOT / "framework" / "policies" / "authority-matrix.yml"
            ).read_text()
            (fw_dir / "authority-matrix.yml").write_text(real_matrix)
            instance_dir = Path(tmpdir) / "instance" / "config"
            instance_dir.mkdir(parents=True)
            (instance_dir / "active-preset").write_text("work")

            input_json = json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": "git push origin main"},
            })

            from io import StringIO
            from policy_engine import main

            env = {"CABINET_ROOT": tmpdir, "OFFICER": "cto"}
            with patch.dict(os.environ, env, clear=False):
                os.environ.pop("CABINET_AUTHORITY_ENFORCING", None)
                with patch("sys.stdin", StringIO(input_json)):
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    assert exc_info.value.code == 0

    def test_main_enforcing_flag_blocks_authority(self):
        """The shadow->enforcing seam is real: with
        CABINET_AUTHORITY_ENFORCING=1, main() DOES exit-2 on a hard-ceiling
        authority action. (Default is 0 = shadow; the flip is a later
        Captain-gated cycle. This proves the flag is load-bearing, not dead.)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            fw_dir = Path(tmpdir) / "framework" / "policies"
            fw_dir.mkdir(parents=True)
            real_matrix = (
                _REPO_ROOT / "framework" / "policies" / "authority-matrix.yml"
            ).read_text()
            (fw_dir / "authority-matrix.yml").write_text(real_matrix)
            instance_dir = Path(tmpdir) / "instance" / "config"
            instance_dir.mkdir(parents=True)
            (instance_dir / "active-preset").write_text("work")

            input_json = json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": "git push origin main"},
            })

            from io import StringIO
            from policy_engine import main

            with patch.dict(os.environ, {
                "CABINET_ROOT": tmpdir,
                "OFFICER": "cto",
                "CABINET_AUTHORITY_ENFORCING": "1",
            }):
                with patch("sys.stdin", StringIO(input_json)):
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    assert exc_info.value.code == 2
