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
