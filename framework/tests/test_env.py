"""CABINET_ENV safety switch — fail-safe by default (dev), opt-in to runtime."""
import os
from pathlib import Path

import pytest

import framework.env as env


class TestCabinetEnv:
    def test_default_is_dev_and_cannot_send(self, monkeypatch):
        monkeypatch.delenv("CABINET_ENV", raising=False)
        assert env.cabinet_env() == "dev"
        assert not env.is_runtime()
        assert not env.allow_sends()          # SAFETY: dev never sends

    def test_runtime_is_explicit_opt_in(self, monkeypatch):
        monkeypatch.setenv("CABINET_ENV", "runtime")
        assert env.is_runtime() and env.allow_sends()

    def test_garbage_value_fails_safe_to_dev(self, monkeypatch):
        monkeypatch.setenv("CABINET_ENV", "prod")   # anything != 'runtime' -> dev
        assert not env.is_runtime() and not env.allow_sends()

    def test_ledger_dir_partitioned_dev_vs_runtime(self, monkeypatch):
        monkeypatch.delenv("CABINET_EVENT_LOG_DIR", raising=False)
        monkeypatch.delenv("CABINET_ENV", raising=False)
        dev = env.ledger_dir()
        monkeypatch.setenv("CABINET_ENV", "runtime")
        run = env.ledger_dir()
        assert dev != run                      # dev proof never mixes into prod
        assert dev.name == "ledger-dev" and run.name == "ledger"

    def test_explicit_ledger_dir_always_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
        assert env.ledger_dir() == tmp_path


@pytest.fixture
def isolated_role_cache():
    """Clear the process-wide captain-role cache for the test, then restore the
    original so sibling tests (which rely on the real 'Head-of-Tech') are
    untouched — mirrors test_clean_room's isolated_captain_cache."""
    saved = env._captain_role_cache
    env._captain_role_cache = None
    try:
        yield
    finally:
        env._captain_role_cache = saved


def _write_cfg(root, name: str, body: str) -> None:
    # NB: single "instance/config" path literal (not "instance" / "config") so
    # the layer-separation gate's bare-"instance" heuristic doesn't flag this
    # test — same form env.py itself uses ("instance/config/platform.yml").
    p = root / "instance/config" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _launcher_instance() -> bool:
    """True only on the original launcher's committed instance/.

    The ``test_this_instance_yields_*`` byte-identity guards below compare
    resolver output against the exact values the removed hardcodes carried —
    values that exist only in the launcher deployment's committed
    instance/config/platform.yml. A fresh hatch (cabinet-init →
    generate-instance.py --adopt) regenerates platform.yml for a NEW captain,
    so on any other instance these guards are meaningless and must SKIP, not
    fail (found by the 2026-07-07 blind-hatch rehearsal: 6 red tests in an
    otherwise-green Testburg clone). Sentinel: the launcher's captain_role
    literal, which this file already asserts."""
    try:
        # Single "instance/config/..." path literal (not "instance"/"config")
        # so the layer-separation gate's bare-"instance" heuristic doesn't
        # flag this test — same form env.py itself uses.
        cfg = os.path.join(os.path.dirname(__file__), "..", "..",
                           "instance/config/platform.yml")
        with open(cfg, encoding="utf-8") as fh:
            return "captain_role: Head-of-Tech" in fh.read()
    except OSError:
        return False


launcher_instance_only = pytest.mark.skipif(
    not _launcher_instance(),
    reason="byte-identity guard — only meaningful on the original launcher's "
           "instance/config/platform.yml (fresh hatches regenerate it)",
)


class TestCaptainRole:
    """The captain_role() resolver — launcher-DRIVEN, fail-closed to generic.

    Sibling of captain_name(): framework code names the Captain's ROLE (e.g. the
    fidelity decision-cell prompt) via this resolver, never a literal. On THIS
    deployment it must render "Head-of-Tech" byte-for-byte."""

    def test_reads_role_from_platform_yml(self, tmp_path, monkeypatch,
                                          isolated_role_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "captain_role: Chief Vibes Officer\n")
        env._captain_role_cache = None
        assert env.captain_role() == "Chief Vibes Officer"

    def test_absent_config_falls_back_to_the_captain(self, tmp_path, monkeypatch,
                                                     isolated_role_cache):
        """No platform.yml / product.yml => the generic default, never a leak."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # empty tmp — no config
        env._captain_role_cache = None
        assert env.captain_role() == "the Captain"
        assert env.captain_role(default="Boss") == "the Captain"  # cached now

    def test_reads_nested_role_from_product_yml(self, tmp_path, monkeypatch,
                                                isolated_role_cache):
        """Single-product deployments nest it under ``product:`` in product.yml."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "product.yml", "product:\n  captain_role: Founder\n")
        env._captain_role_cache = None
        assert env.captain_role() == "Founder"

    def test_platform_yml_wins_over_product_yml(self, tmp_path, monkeypatch,
                                                isolated_role_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "captain_role: Head-of-Tech\n")
        _write_cfg(tmp_path, "product.yml", "product:\n  captain_role: Founder\n")
        env._captain_role_cache = None
        assert env.captain_role() == "Head-of-Tech"


@pytest.fixture
def isolated_slug_cache():
    """Clear the process-wide captain-slug cache for the test, then restore the
    original so sibling tests are untouched (mirrors isolated_role_cache)."""
    saved = env._captain_slug_cache
    env._captain_slug_cache = None
    try:
        yield
    finally:
        env._captain_slug_cache = saved


class TestCaptainSlug:
    """The captain_slug() resolver — the officer_tasks OWNER slug that marks a
    row as the Captain's (the reminder arm routes it to the needs-card surface).
    A ROLE token, never a display name: the generic default is the literal
    ``captain`` (the /tasks ETL + events-schema convention), config-overridable,
    fail-closed to generic — never a leaked launcher name."""

    def test_absent_config_falls_back_to_captain(self, tmp_path, monkeypatch,
                                                 isolated_slug_cache):
        monkeypatch.delenv("CABINET_CAPTAIN_SLUG", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # empty tmp — no config
        env._captain_slug_cache = None
        assert env.captain_slug() == "captain"

    def test_env_override_wins(self, tmp_path, monkeypatch, isolated_slug_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "captain_slug: skipper\n")
        monkeypatch.setenv("CABINET_CAPTAIN_SLUG", "helm")
        env._captain_slug_cache = None
        assert env.captain_slug() == "helm"   # env beats config

    def test_reads_slug_from_platform_yml(self, tmp_path, monkeypatch,
                                          isolated_slug_cache):
        monkeypatch.delenv("CABINET_CAPTAIN_SLUG", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "captain_slug: skipper\n")
        env._captain_slug_cache = None
        assert env.captain_slug() == "skipper"

    def test_reads_nested_slug_from_product_yml(self, tmp_path, monkeypatch,
                                                isolated_slug_cache):
        monkeypatch.delenv("CABINET_CAPTAIN_SLUG", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "product.yml", "product:\n  captain_slug: skipper\n")
        env._captain_slug_cache = None
        assert env.captain_slug() == "skipper"

    def test_never_leaks_a_personal_name_by_default(self, tmp_path, monkeypatch,
                                                    isolated_slug_cache):
        """The default is a generic role token — never captain_name()'s value."""
        monkeypatch.delenv("CABINET_CAPTAIN_SLUG", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "captain_name: Wendy Wanderlust\n")
        env._captain_slug_cache = None
        assert env.captain_slug() == "captain"   # name never becomes the slug

    def test_result_is_cached_process_wide(self, tmp_path, monkeypatch,
                                           isolated_role_cache):
        """First resolution wins for the process (a restart re-reads)."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "captain_role: First\n")
        env._captain_role_cache = None
        assert env.captain_role() == "First"
        _write_cfg(tmp_path, "platform.yml", "captain_role: Second\n")  # ignored
        assert env.captain_role() == "First"

    @launcher_instance_only
    def test_this_instance_yields_head_of_tech(self, monkeypatch,
                                               isolated_role_cache):
        """Byte-identity guard: with CABINET_ROOT unset the resolver finds the
        repo via env.py's file-relative parents[N] and reads THIS worktree's
        instance/config/platform.yml, which yields Head-of-Tech — so the
        decision-cell prompt renders identically to the removed hardcode."""
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        env._captain_role_cache = None
        assert env.captain_role() == "Head-of-Tech"


@pytest.fixture
def isolated_org_domains_cache():
    """Clear the process-wide org-domains cache for the test, then restore the
    original so sibling tests (which rely on the real instance domains, incl. the
    action-classifier import that binds them) are untouched — mirrors
    isolated_role_cache."""
    saved = env._org_domains_cache
    env._org_domains_cache = None
    try:
        yield
    finally:
        env._org_domains_cache = saved


@pytest.fixture
def isolated_tasks_board_cache():
    """Clear the process-wide tasks-board cache for the test, then restore the
    original so sibling tests (action_exec.DEFAULT_TASKS_BOARD, the canary) are
    untouched — mirrors isolated_role_cache."""
    saved = env._tasks_board_cache
    env._tasks_board_cache = None
    try:
        yield
    finally:
        env._tasks_board_cache = saved


class TestOrgDomains:
    """The org_domains() resolver — instance-DRIVEN, fail-closed to EMPTY.

    The action classifier (framework/authority/classifier.py) reads its
    internal-vs-external domain list via this resolver, never a literal. On THIS
    deployment it must return the same six domains the removed hardcode had, so
    recipient classification is byte-identical."""

    def test_reads_domains_from_platform_yml(self, tmp_path, monkeypatch,
                                             isolated_org_domains_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml",
                   "org_domains:\n  - acme.com\n  - acme.io\n")
        env._org_domains_cache = None
        assert env.org_domains() == ("acme.com", "acme.io")

    def test_absent_config_fails_closed_to_empty(self, tmp_path, monkeypatch,
                                                 isolated_org_domains_cache):
        """No platform.yml / product.yml => the EMPTY tuple: a generic
        deployment treats every recipient as external, never leaks a domain."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # empty tmp — no config
        env._org_domains_cache = None
        assert env.org_domains() == ()

    def test_entries_stripped_and_lowercased_order_preserved(
            self, tmp_path, monkeypatch, isolated_org_domains_cache):
        """The is_internal predicate compares against an already-lowercased
        recipient domain, so config entries are normalized; order is preserved."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml",
                   "org_domains:\n  - '  Testburg.EXAMPLE '\n  - Second.Example\n")
        env._org_domains_cache = None
        assert env.org_domains() == ("testburg.example", "second.example")

    def test_reads_nested_domains_from_product_yml(self, tmp_path, monkeypatch,
                                                   isolated_org_domains_cache):
        """Single-product deployments nest it under ``product:`` in product.yml."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "product.yml",
                   "product:\n  org_domains:\n    - solo.example\n")
        env._org_domains_cache = None
        assert env.org_domains() == ("solo.example",)

    def test_result_is_cached_process_wide(self, tmp_path, monkeypatch,
                                           isolated_org_domains_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "org_domains:\n  - first.example\n")
        env._org_domains_cache = None
        assert env.org_domains() == ("first.example",)
        _write_cfg(tmp_path, "platform.yml", "org_domains:\n  - second.example\n")
        assert env.org_domains() == ("first.example",)   # cached, second ignored

    @launcher_instance_only
    def test_this_instance_yields_the_six_org_domains(self, monkeypatch,
                                                      isolated_org_domains_cache):
        """Byte-identity guard: with CABINET_ROOT unset the resolver reads THIS
        worktree's instance/config/platform.yml, yielding exactly the domains
        that file declares — so is_internal is byte-identical. The expected
        list is derived from the on-disk YAML itself (never a hardcoded
        literal here, mirroring env.org_domains's own local `import yaml`
        idiom), so this framework-layer test carries no instance-specific
        domain of its own; a fresh hatch's regenerated platform.yml correctly
        SKIPS this guard via launcher_instance_only."""
        import yaml
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        env._org_domains_cache = None
        cfg = os.path.join(os.path.dirname(__file__), "..", "..",
                           "instance/config/platform.yml")
        with open(cfg, encoding="utf-8") as fh:
            declared = yaml.safe_load(fh).get("org_domains") or []
        expected = tuple(d.strip().lower() for d in declared
                         if isinstance(d, str) and d.strip())
        assert expected, "the launcher's real platform.yml must declare org_domains"
        assert env.org_domains() == expected


class TestTasksBoard:
    """The tasks_board() resolver — instance-DRIVEN, fail-closed to "".

    action_exec's DEFAULT_TASKS_BOARD and the act-first canary read the board id
    via this resolver, never a literal. On THIS deployment it must return
    exactly the board id the live platform.yml declares, so the executor +
    canary are byte-identical."""

    def test_reads_board_from_platform_yml(self, tmp_path, monkeypatch,
                                           isolated_tasks_board_cache):
        monkeypatch.delenv("CABINET_TASKS_BOARD", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", 'tasks_board: "42424242"\n')
        env._tasks_board_cache = None
        assert env.tasks_board() == "42424242"

    def test_absent_config_fails_closed_to_empty(self, tmp_path, monkeypatch,
                                                 isolated_tasks_board_cache):
        """No board configured => "" — the executor's isdigit() guard refuses
        rather than landing on another deployment's board."""
        monkeypatch.delenv("CABINET_TASKS_BOARD", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # empty tmp — no config
        env._tasks_board_cache = None
        assert env.tasks_board() == ""

    def test_env_override_wins_over_config(self, tmp_path, monkeypatch,
                                           isolated_tasks_board_cache):
        """CABINET_TASKS_BOARD mirrors action_exec's ACTION_LANE_DEFAULT_BOARD —
        an explicit per-process override beats the configured board."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", 'tasks_board: "11111111"\n')
        monkeypatch.setenv("CABINET_TASKS_BOARD", "99999999")
        env._tasks_board_cache = None
        assert env.tasks_board() == "99999999"

    def test_reads_nested_board_from_product_yml(self, tmp_path, monkeypatch,
                                                 isolated_tasks_board_cache):
        monkeypatch.delenv("CABINET_TASKS_BOARD", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "product.yml",
                   'product:\n  tasks_board: "22222222"\n')
        env._tasks_board_cache = None
        assert env.tasks_board() == "22222222"

    @launcher_instance_only
    def test_this_instance_yields_the_tasks_board(self, monkeypatch,
                                                  isolated_tasks_board_cache):
        """Byte-identity guard: the resolver returns exactly the tasks_board
        THIS worktree's platform.yml declares, so DEFAULT_TASKS_BOARD + the
        canary probe board are byte-identical. The expected id is derived
        from the on-disk YAML itself (never a hardcoded literal here — the
        same idiom as the org_domains guard above), so no deployment's board
        id ships in this test."""
        import yaml
        monkeypatch.delenv("CABINET_TASKS_BOARD", raising=False)
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        env._tasks_board_cache = None
        cfg = os.path.join(os.path.dirname(__file__), "..", "..",
                           "instance/config/platform.yml")
        with open(cfg, encoding="utf-8") as fh:
            declared = str((yaml.safe_load(fh) or {}).get("tasks_board") or "")
        assert declared and declared.isdigit(), \
            "the launcher's real platform.yml must declare tasks_board"
        assert env.tasks_board() == declared


@pytest.fixture
def isolated_timezone_cache():
    """Clear the process-wide captain-timezone cache for the test, then restore
    the original so sibling tests (and screenpipe_adapter._captain_tz, which
    resolves the real 'Europe/Berlin') are untouched — mirrors
    isolated_role_cache."""
    saved = env._captain_timezone_cache
    env._captain_timezone_cache = None
    try:
        yield
    finally:
        env._captain_timezone_cache = saved


class TestCaptainTimezone:
    """The captain_timezone() resolver — launcher-DRIVEN, fail-closed to the
    generic Central-European Europe/Berlin (CET/CEST) fallback.

    screenpipe_adapter._captain_tz() resolves the 'today'-boundary timezone NAME
    via this resolver, never a hand-read of platform.yml. On THIS deployment it
    must return "Europe/Berlin" byte-for-byte, so the greeting-of-the-day
    boundary is identical to the removed hand-reader."""

    def test_reads_timezone_from_platform_yml(self, tmp_path, monkeypatch,
                                              isolated_timezone_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "captain_timezone: America/New_York\n")
        env._captain_timezone_cache = None
        assert env.captain_timezone() == "America/New_York"

    def test_inline_comment_is_stripped(self, tmp_path, monkeypatch,
                                        isolated_timezone_cache):
        """The live platform.yml carries a trailing '# CEST/CET' comment; yaml
        drops it so the resolver returns the bare IANA name (byte-identity with
        the hand-reader's split('#') behaviour)."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml",
                   "captain_timezone: Europe/Berlin   # CEST/CET — DST\n")
        env._captain_timezone_cache = None
        assert env.captain_timezone() == "Europe/Berlin"

    def test_absent_config_falls_back_to_europe_berlin(self, tmp_path, monkeypatch,
                                                       isolated_timezone_cache):
        """No platform.yml / product.yml => the generic Europe/Berlin fallback —
        the SAME default the removed hand-reader carried, never a crash."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # empty tmp — no config
        env._captain_timezone_cache = None
        assert env.captain_timezone() == "Europe/Berlin"
        assert env.captain_timezone(default="UTC") == "Europe/Berlin"  # cached now

    def test_reads_nested_timezone_from_product_yml(self, tmp_path, monkeypatch,
                                                    isolated_timezone_cache):
        """Single-product deployments nest it under ``product:`` in product.yml."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "product.yml",
                   "product:\n  captain_timezone: Asia/Tokyo\n")
        env._captain_timezone_cache = None
        assert env.captain_timezone() == "Asia/Tokyo"

    def test_platform_yml_wins_over_product_yml(self, tmp_path, monkeypatch,
                                                isolated_timezone_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "captain_timezone: Europe/Berlin\n")
        _write_cfg(tmp_path, "product.yml",
                   "product:\n  captain_timezone: Asia/Tokyo\n")
        env._captain_timezone_cache = None
        assert env.captain_timezone() == "Europe/Berlin"

    def test_result_is_cached_process_wide(self, tmp_path, monkeypatch,
                                           isolated_timezone_cache):
        """First resolution wins for the process (a restart re-reads)."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "captain_timezone: America/New_York\n")
        env._captain_timezone_cache = None
        assert env.captain_timezone() == "America/New_York"
        _write_cfg(tmp_path, "platform.yml", "captain_timezone: Asia/Tokyo\n")  # ignored
        assert env.captain_timezone() == "America/New_York"

    @launcher_instance_only
    def test_this_instance_yields_europe_berlin(self, monkeypatch,
                                                isolated_timezone_cache):
        """Byte-identity guard: with CABINET_ROOT unset the resolver finds the
        repo via env.py's file-relative parents[N] and reads THIS worktree's
        instance/config/platform.yml, which yields Europe/Berlin — so
        _captain_tz() renders the identical zone to the removed hand-reader."""
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        env._captain_timezone_cache = None
        assert env.captain_timezone() == "Europe/Berlin"


@pytest.fixture
def isolated_vault_dir_cache():
    """Clear the process-wide vault-dir cache for the test, then restore the
    original so sibling code (decision_cell._vault_dir) is untouched — mirrors
    isolated_tasks_board_cache."""
    saved = env._vault_dir_cache
    env._vault_dir_cache = None
    try:
        yield
    finally:
        env._vault_dir_cache = saved


@pytest.fixture
def isolated_state_dir_cache():
    """Clear the process-wide state-dir cache for the test, then restore the
    original so sibling code (benchmark._DEFAULT_OUTCOMES, watchdog.registry's
    PERSONAL_SOURCE_STATE_DIR) is untouched — mirrors isolated_tasks_board_cache."""
    saved = env._state_dir_cache
    env._state_dir_cache = None
    try:
        yield
    finally:
        env._state_dir_cache = saved


class TestVaultDir:
    """The vault_dir() resolver — instance-DRIVEN, fail-closed to "".

    The fidelity decision-cell (framework/fidelity/decision_cell.py) reads the
    brain vault dir via this resolver, never a literal. On THIS deployment it must
    return the brain vault (byte-identical to the removed vault hardcode) so the
    Decisions corpus resolves the same files; a clean-room box resolves "" and
    the corpus is simply empty."""

    def test_reads_vault_from_platform_yml(self, tmp_path, monkeypatch,
                                           isolated_vault_dir_cache):
        monkeypatch.delenv("CABINET_VAULT_DIR", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "vault_dir: /tmp/some/vault\n")
        env._vault_dir_cache = None
        assert env.vault_dir() == "/tmp/some/vault"

    def test_leading_tilde_is_expanded(self, tmp_path, monkeypatch,
                                       isolated_vault_dir_cache):
        monkeypatch.delenv("CABINET_VAULT_DIR", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "vault_dir: ~/some/vault\n")
        env._vault_dir_cache = None
        assert env.vault_dir() == os.path.expanduser("~/some/vault")

    def test_absent_config_fails_closed_to_empty(self, tmp_path, monkeypatch,
                                                 isolated_vault_dir_cache):
        """No vault configured => "" — the caller then treats the corpus as
        empty (no vault ⇒ no cases), never reads another deployment's vault."""
        monkeypatch.delenv("CABINET_VAULT_DIR", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # empty tmp — no config
        env._vault_dir_cache = None
        assert env.vault_dir() == ""

    def test_env_override_wins_over_config_and_expands(self, tmp_path, monkeypatch,
                                                       isolated_vault_dir_cache):
        """CABINET_VAULT_DIR is an explicit per-process override; a leading ~ is
        expanded exactly like the config path."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "vault_dir: /tmp/cfg/vault\n")
        monkeypatch.setenv("CABINET_VAULT_DIR", "~/env/vault")
        env._vault_dir_cache = None
        assert env.vault_dir() == os.path.expanduser("~/env/vault")

    def test_reads_nested_vault_from_product_yml(self, tmp_path, monkeypatch,
                                                 isolated_vault_dir_cache):
        monkeypatch.delenv("CABINET_VAULT_DIR", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "product.yml",
                   "product:\n  vault_dir: /tmp/nested/vault\n")
        env._vault_dir_cache = None
        assert env.vault_dir() == "/tmp/nested/vault"

    @launcher_instance_only
    def test_this_instance_yields_the_brain_vault(self, monkeypatch,
                                                  isolated_vault_dir_cache):
        """Byte-identity guard: with CABINET_ROOT unset the resolver reads THIS
        worktree's instance/config/platform.yml, yielding the brain vault — so
        decision_cell._vault_dir() resolves the identical Decisions corpus to the
        removed hardcode."""
        monkeypatch.delenv("CABINET_VAULT_DIR", raising=False)
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        env._vault_dir_cache = None
        assert env.vault_dir() == os.path.expanduser("~/obsidian/screenpipe-brain")


class TestStateDir:
    """The state_dir() resolver — instance-DRIVEN, fail-closed to "".

    The fidelity decision-cache + autonomy-outcomes ledger (benchmark) and the
    outcome-watchdog's watched pipe dir (framework/watchdog/registry.py) read the
    personal-source state dir via this resolver, never a literal. On THIS
    deployment it must return the brain state dir (byte-identical to the removed
    state hardcode); a clean-room box resolves "" (nothing-to-watch degrade)."""

    def test_reads_state_from_platform_yml(self, tmp_path, monkeypatch,
                                           isolated_state_dir_cache):
        monkeypatch.delenv("CABINET_STATE_DIR", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "state_dir: /tmp/some/state\n")
        env._state_dir_cache = None
        assert env.state_dir() == "/tmp/some/state"

    def test_leading_tilde_is_expanded(self, tmp_path, monkeypatch,
                                       isolated_state_dir_cache):
        monkeypatch.delenv("CABINET_STATE_DIR", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "state_dir: ~/some/state\n")
        env._state_dir_cache = None
        assert env.state_dir() == os.path.expanduser("~/some/state")

    def test_absent_config_fails_closed_to_empty(self, tmp_path, monkeypatch,
                                                 isolated_state_dir_cache):
        """No state dir configured => "" — the watchdog then treats it as
        nothing-to-watch; cache/outcomes callers substitute their own generic
        ~/.cabinet/state; never another deployment's state."""
        monkeypatch.delenv("CABINET_STATE_DIR", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # empty tmp — no config
        env._state_dir_cache = None
        assert env.state_dir() == ""

    def test_env_override_wins_over_config_and_expands(self, tmp_path, monkeypatch,
                                                       isolated_state_dir_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "state_dir: /tmp/cfg/state\n")
        monkeypatch.setenv("CABINET_STATE_DIR", "~/env/state")
        env._state_dir_cache = None
        assert env.state_dir() == os.path.expanduser("~/env/state")

    def test_reads_nested_state_from_product_yml(self, tmp_path, monkeypatch,
                                                 isolated_state_dir_cache):
        monkeypatch.delenv("CABINET_STATE_DIR", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "product.yml",
                   "product:\n  state_dir: /tmp/nested/state\n")
        env._state_dir_cache = None
        assert env.state_dir() == "/tmp/nested/state"

    @launcher_instance_only
    def test_this_instance_yields_the_brain_state_dir(self, monkeypatch,
                                                      isolated_state_dir_cache):
        """Byte-identity guard: with CABINET_ROOT unset the resolver reads THIS
        worktree's instance/config/platform.yml, yielding the brain state dir —
        so the decision-cache / outcomes / watched paths resolve identically to
        the removed hardcode."""
        monkeypatch.delenv("CABINET_STATE_DIR", raising=False)
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        env._state_dir_cache = None
        assert env.state_dir() == os.path.expanduser("~/.screenpipe/state")


@pytest.fixture
def isolated_git_repos_cache():
    """Clear the process-wide git-repos cache for the test, then restore the
    original so sibling tests (the fidelity decision-cell's real git corpus)
    are untouched — mirrors isolated_org_domains_cache."""
    saved = env._git_repos_cache
    env._git_repos_cache = None
    try:
        yield
    finally:
        env._git_repos_cache = saved


class TestGitRepos:
    """The git_repos() resolver — instance-DRIVEN, fail-closed to EMPTY.

    The fidelity decision-cell's git-derived DecisionCases corpus
    (framework/fidelity/decision_cell.py build_decision_corpus's "git" source)
    reads its default repo list via this resolver, never a literal. On THIS
    deployment it must return the same two repos the removed hardcode had, so
    the git corpus is byte-identical."""

    def test_reads_repos_from_platform_yml(self, tmp_path, monkeypatch,
                                           isolated_git_repos_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml",
                   "git_repos:\n  - /tmp/repo-a\n  - /tmp/repo-b\n")
        env._git_repos_cache = None
        assert env.git_repos() == (Path("/tmp/repo-a"), Path("/tmp/repo-b"))

    def test_absent_config_fails_closed_to_empty(self, tmp_path, monkeypatch,
                                                 isolated_git_repos_cache):
        """No platform.yml / product.yml => the EMPTY tuple: a generic
        deployment mines no git repos, never crashes, never leaks a path."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # empty tmp — no config
        env._git_repos_cache = None
        assert env.git_repos() == ()

    def test_leading_tilde_is_expanded_order_preserved(
            self, tmp_path, monkeypatch, isolated_git_repos_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml",
                   "git_repos:\n  - ~/repo-one\n  - ~/repo-two\n")
        env._git_repos_cache = None
        assert env.git_repos() == (Path("~/repo-one").expanduser(),
                                    Path("~/repo-two").expanduser())

    def test_reads_nested_repos_from_product_yml(self, tmp_path, monkeypatch,
                                                 isolated_git_repos_cache):
        """Single-product deployments nest it under ``product:`` in product.yml."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "product.yml",
                   "product:\n  git_repos:\n    - /tmp/solo-repo\n")
        env._git_repos_cache = None
        assert env.git_repos() == (Path("/tmp/solo-repo"),)

    def test_result_is_cached_process_wide(self, tmp_path, monkeypatch,
                                           isolated_git_repos_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "git_repos:\n  - /tmp/first\n")
        env._git_repos_cache = None
        assert env.git_repos() == (Path("/tmp/first"),)
        _write_cfg(tmp_path, "platform.yml", "git_repos:\n  - /tmp/second\n")
        assert env.git_repos() == (Path("/tmp/first"),)   # cached, second ignored

    @launcher_instance_only
    def test_this_instance_yields_the_two_git_repos(self, monkeypatch,
                                                     isolated_git_repos_cache):
        """Byte-identity guard: with CABINET_ROOT unset the resolver reads THIS
        worktree's instance/config/platform.yml, yielding the exact two repos
        the decision_cell hardcode carried — so the git corpus is byte-identical."""
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        env._git_repos_cache = None
        assert env.git_repos() == (Path.home() / "v0-politiske-annoncer",
                                    Path.home() / "dev-tasks")


class TestWatchdogConfigPath:
    """watchdog_config_path() — the seam that lifts the outcome-watchdog's
    instance/config/watchdog.yml PATH out of framework/watchdog/registry.py
    (layer-separation gate). Path-only resolver: the registry owns the parse
    and its generic fail-safe defaults, so any resolution failure ("") reads
    as an absent file — same degrade as before the move."""

    def test_resolves_under_cabinet_root(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CABINET_WATCHDOG_CONFIG", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        # NB: joined "instance/config/..." literal — the same seam idiom
        # env.py uses; the layer-sep gate flags only the bare token.
        assert env.watchdog_config_path() == str(
            tmp_path / "instance/config/watchdog.yml")

    def test_env_override_wins_and_expands(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        monkeypatch.setenv("CABINET_WATCHDOG_CONFIG", "~/wd/watchdog.yml")
        assert env.watchdog_config_path() == os.path.expanduser("~/wd/watchdog.yml")

    def test_this_instance_resolves_the_repo_config(self, monkeypatch):
        """Byte-identity guard: with CABINET_ROOT unset the resolver yields
        THIS checkout's instance watchdog config — identical to the joined
        path the registry used to build itself."""
        monkeypatch.delenv("CABINET_WATCHDOG_CONFIG", raising=False)
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        import pathlib
        repo = pathlib.Path(env.__file__).resolve().parents[1]
        assert env.watchdog_config_path() == str(
            repo / "instance/config/watchdog.yml")


class TestActivePreset:
    """active_preset() — the instance-side pointer the onboarding planner
    resolves through the env seam (the presets DIR itself stays a caller
    parameter — payload, not instance config)."""

    def test_reads_active_preset_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CABINET_ACTIVE_PRESET", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        p = tmp_path / "instance/config" / "active-preset"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("portfolio\n", encoding="utf-8")
        assert env.active_preset() == "portfolio"

    def test_absent_file_falls_back_to_work(self, tmp_path, monkeypatch):
        """Mirrors load-preset.sh: unset deployments resolve 'work' on both
        sides of the seam."""
        monkeypatch.delenv("CABINET_ACTIVE_PRESET", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # empty tmp — no config
        assert env.active_preset() == "work"

    def test_blank_file_falls_back_to_work(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CABINET_ACTIVE_PRESET", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        p = tmp_path / "instance/config" / "active-preset"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("   \n", encoding="utf-8")
        assert env.active_preset() == "work"

    def test_env_override_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        p = tmp_path / "instance/config" / "active-preset"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("portfolio\n", encoding="utf-8")
        monkeypatch.setenv("CABINET_ACTIVE_PRESET", "acme")
        assert env.active_preset() == "acme"


# ---------------------------------------------------------------------------
# Lane / officer roster resolvers (PC-E-LOCKSTEP instance-split, Wave G)
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_officers_cache():
    """Clear the process-wide officers cache for the test, then restore the
    original so sibling tests are untouched — mirrors isolated_role_cache."""
    saved = env._officers_cache
    env._officers_cache = None
    try:
        yield
    finally:
        env._officers_cache = saved


@pytest.fixture
def isolated_deploys_code_officer_cache():
    saved = env._deploys_code_officer_cache
    env._deploys_code_officer_cache = None
    try:
        yield
    finally:
        env._deploys_code_officer_cache = saved


@pytest.fixture
def isolated_lanes_cache():
    saved = env._lanes_cache
    env._lanes_cache = None
    try:
        yield
    finally:
        env._lanes_cache = saved


@pytest.fixture
def isolated_lane_default_cache():
    saved = env._lane_default_cache
    env._lane_default_cache = None
    try:
        yield
    finally:
        env._lane_default_cache = saved


def _write_conf(root, body: str) -> None:
    p = root / "cabinet" / "officer-capabilities.conf"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _write_context(root, name: str, body: str) -> None:
    # Single "instance/config" path literal — same layer-separation-gate note
    # as _write_cfg above.
    p = root / "instance/config" / "contexts" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


_TESTBURG_CONF = """# Testburg fixture roster
# comment line with a colon: ignored
town-crier:captain_rules_retrieval
town-crier:logs_captain_decisions

bakery-ceo:deploys_code
bakery-ceo:logs_captain_decisions
market-ceo:deploys_code
market-ceo:captain_rules_retrieval
"""


class TestOfficers:
    """The officers() resolver — instance-DRIVEN, fail-closed to EMPTY.

    The officer whitelist / prompt-enum / roster surfaces read the roster via
    this resolver, never a baked-in literal set (PC-E-LOCKSTEP pair (a)/(e)
    consumers land at the germline ceremony; this pins the resolver they bind
    to). Fixture vocabulary is synthetic Testburg — never instance lanes."""

    def test_reads_officer_column_file_order_deduped(
            self, tmp_path, monkeypatch, isolated_officers_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_conf(tmp_path, _TESTBURG_CONF)
        env._officers_cache = None
        assert env.officers() == ("town-crier", "bakery-ceo", "market-ceo")

    def test_dedup_is_global_first_seen_not_adjacent_only(
            self, tmp_path, monkeypatch, isolated_officers_cache):
        # INTERLEAVED (non-contiguous) officer blocks — the twin-divergence
        # trap the officers() docstring prescribes for the bash twin
        # (awk '!seen[$1]++', NEVER adjacent-only `uniq`). A regression to
        # adjacent-only dedup in either twin would emit town-crier twice
        # here; _TESTBURG_CONF above is contiguous-only and cannot catch it.
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_conf(tmp_path, (
            "town-crier:captain_rules_retrieval\n"
            "bakery-ceo:deploys_code\n"
            "town-crier:logs_captain_decisions\n"
        ))
        env._officers_cache = None
        assert env.officers() == ("town-crier", "bakery-ceo")

    def test_comments_blanks_and_malformed_lines_skipped(
            self, tmp_path, monkeypatch, isolated_officers_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_conf(tmp_path,
                    "# header\n\nnot-a-row\nbakery-ceo:deploys_code\n")
        env._officers_cache = None
        assert env.officers() == ("bakery-ceo",)

    def test_absent_conf_fails_closed_to_empty(
            self, tmp_path, monkeypatch, isolated_officers_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # empty tmp — no conf
        env._officers_cache = None
        assert env.officers() == ()

    def test_caller_default_honored_when_unreadable(
            self, tmp_path, monkeypatch, isolated_officers_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        env._officers_cache = None
        assert env.officers(default=("town-crier",)) == ("town-crier",)

    def test_result_is_cached_process_wide(
            self, tmp_path, monkeypatch, isolated_officers_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_conf(tmp_path, "bakery-ceo:deploys_code\n")
        env._officers_cache = None
        assert env.officers() == ("bakery-ceo",)
        _write_conf(tmp_path, "market-ceo:deploys_code\n")  # ignored — cached
        assert env.officers() == ("bakery-ceo",)


class TestDeploysCodeOfficer:
    """The deploys_code_officer() resolver — first conf-file-order holder,
    fail-closed to "" (an eval consumer then prints FAIL, never probes a
    baked-in officer)."""

    def test_first_holder_in_file_order(
            self, tmp_path, monkeypatch, isolated_deploys_code_officer_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_conf(tmp_path, _TESTBURG_CONF)
        env._deploys_code_officer_cache = None
        assert env.deploys_code_officer() == "bakery-ceo"

    def test_no_holder_fails_closed_to_empty(
            self, tmp_path, monkeypatch, isolated_deploys_code_officer_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_conf(tmp_path, "town-crier:logs_captain_decisions\n")
        env._deploys_code_officer_cache = None
        assert env.deploys_code_officer() == ""

    def test_absent_conf_fails_closed_to_empty(
            self, tmp_path, monkeypatch, isolated_deploys_code_officer_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        env._deploys_code_officer_cache = None
        assert env.deploys_code_officer() == ""


class TestLanes:
    """The lanes() resolver — the instance context-slug enum, fail-closed to
    EMPTY. Parse mirrors run_action_lane._context_slugs byte-for-byte so the
    two can merge at a germline window."""

    def test_reads_sorted_slugs_from_contexts(
            self, tmp_path, monkeypatch, isolated_lanes_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_context(tmp_path, "testburg.yml", "slug: testburg\nactive: true\n")
        _write_context(tmp_path, "market.yml", 'slug: "testburg-market"\n')
        _write_context(tmp_path, "harbor.yml", "slug: 'Testburg-Harbor'\n")
        env._lanes_cache = None
        assert env.lanes() == ("testburg", "testburg-harbor", "testburg-market")

    def test_file_without_slug_skipped(
            self, tmp_path, monkeypatch, isolated_lanes_cache):
        """_default.yml has no slug: scalar — skipped, exactly like the
        acting-lane parser skips it."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_context(tmp_path, "_default.yml", "description: defaults only\n")
        _write_context(tmp_path, "testburg.yml", "slug: testburg\n")
        env._lanes_cache = None
        assert env.lanes() == ("testburg",)

    def test_active_false_context_still_enumerated(
            self, tmp_path, monkeypatch, isolated_lanes_cache):
        """THE recon-named trap: a context declared active: false can still
        have a RUNNING lane officer — the enum must NEVER filter on active:
        (an activation-filtered enum would silently drop live lanes)."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_context(tmp_path, "dormant.yml",
                       "slug: testburg-dormant\nactive: false\n")
        env._lanes_cache = None
        assert env.lanes() == ("testburg-dormant",)

    def test_absent_dir_fails_closed_to_empty(
            self, tmp_path, monkeypatch, isolated_lanes_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # no contexts dir
        env._lanes_cache = None
        assert env.lanes() == ()
        env._lanes_cache = None
        assert env.lanes(default=("testburg",)) == ("testburg",)

    def test_result_is_cached_process_wide(
            self, tmp_path, monkeypatch, isolated_lanes_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_context(tmp_path, "testburg.yml", "slug: testburg\n")
        env._lanes_cache = None
        assert env.lanes() == ("testburg",)
        _write_context(tmp_path, "more.yml", "slug: testburg-more\n")  # ignored
        assert env.lanes() == ("testburg",)


class TestLaneDefault:
    """The lane_default() resolver — instance-DRIVEN, fail-closed to "".

    PC-E-LOCKSTEP pair (e): the acting lane's proposal default lane is a
    Captain ruling encoded as instance data; a generic deployment resolves ""
    and the runner's lane normalization files cards under the stable adhoc
    catch-all."""

    def test_reads_from_platform_yml(
            self, tmp_path, monkeypatch, isolated_lane_default_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "lane_default: testburg\n")
        env._lane_default_cache = None
        assert env.lane_default() == "testburg"

    def test_reads_nested_product_yml(
            self, tmp_path, monkeypatch, isolated_lane_default_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "product.yml",
                   "product:\n  lane_default: testburg-market\n")
        env._lane_default_cache = None
        assert env.lane_default() == "testburg-market"

    def test_platform_yml_wins_over_product_yml(
            self, tmp_path, monkeypatch, isolated_lane_default_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "lane_default: testburg\n")
        _write_cfg(tmp_path, "product.yml",
                   "product:\n  lane_default: testburg-market\n")
        env._lane_default_cache = None
        assert env.lane_default() == "testburg"

    def test_absent_config_fails_closed_to_empty(
            self, tmp_path, monkeypatch, isolated_lane_default_cache):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # empty tmp — no config
        env._lane_default_cache = None
        assert env.lane_default() == ""


class TestActiveContext:
    """active_context() — the preset-aware tasks/coordination context chain
    (config-split fix 2026-07-17). Full rung matrix + bash-twin PARITY lives
    in cabinet/scripts/lib/tests/test_resolve_context_sh.py; this class pins
    the env.py-local contract: root-injectability, uncached-ness, the shape
    gate, and never-raise fail-safe."""

    @staticmethod
    def _seed(tmp_path, contexts, platform_yml=None, active_project=None):
        # NB: single "instance/config" path literal (not split segments) so the
        # layer-separation gate's bare-"instance" heuristic doesn't flag this
        # test — the _write_cfg idiom above, same form env.py itself uses.
        cfg = tmp_path / "instance/config"
        (cfg / "contexts").mkdir(parents=True, exist_ok=True)
        for name, body in contexts.items():
            (cfg / "contexts" / name).write_text(body, encoding="utf-8")
        if platform_yml is not None:
            (cfg / "platform.yml").write_text(platform_yml, encoding="utf-8")
        if active_project is not None:
            (cfg / "active-project.txt").write_text(
                active_project, encoding="utf-8")
        return tmp_path

    def test_env_var_wins(self, tmp_path, monkeypatch):
        self._seed(tmp_path, {"bakery.yml": "slug: bakery\n"},
                   active_project="bakery\n")
        monkeypatch.setenv("CABINET_CONTEXT", "testburg-hq")
        assert env.active_context(root=tmp_path) == "testburg-hq"

    def test_malformed_env_var_skipped_never_returned(self, tmp_path, monkeypatch):
        """Shape gate: an injection-shaped env value falls through as
        unresolved data — it is never the return value."""
        self._seed(tmp_path, {"bakery.yml": "slug: bakery\n"})
        monkeypatch.setenv("CABINET_CONTEXT", "../../etc; $(rm -rf .)")
        assert env.active_context(root=tmp_path) == "bakery"

    def test_officer_lane_derivation_longest_prefix(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CABINET_CONTEXT", raising=False)
        self._seed(tmp_path, {"bakery.yml": "slug: bakery\n",
                              "bakery-site.yml": "slug: bakery-site\n"})
        assert env.active_context(officer="bakery-site-ceo",
                                  root=tmp_path) == "bakery-site"

    def test_lane_default_only_when_declared(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CABINET_CONTEXT", raising=False)
        self._seed(tmp_path, {"bakery.yml": "slug: bakery\n",
                              "newsletter.yml": "slug: newsletter\n"},
                   platform_yml="lane_default: ghost-lane\n")
        assert env.active_context(officer="cos", root=tmp_path) == ""
        (tmp_path / "instance/config" / "platform.yml").write_text(
            "lane_default: newsletter\n", encoding="utf-8")
        assert env.active_context(officer="cos", root=tmp_path) == "newsletter"

    def test_uncached_across_roots_and_config_flips(self, tmp_path, monkeypatch):
        """Deliberately UNCACHED (unlike lanes()/lane_default()): the same
        process must see a different root — and a config flip — immediately."""
        monkeypatch.delenv("CABINET_CONTEXT", raising=False)
        a = self._seed(tmp_path / "a", {"bakery.yml": "slug: bakery\n"})
        b = self._seed(tmp_path / "b", {"newsletter.yml": "slug: newsletter\n"})
        assert env.active_context(root=a) == "bakery"
        assert env.active_context(root=b) == "newsletter"
        (a / "instance/config" / "active-project.txt").write_text(
            "newsletter\n", encoding="utf-8")
        # flip lands without any cache reset — but the slug must be declared?
        # No: R2 is the operator's explicit file, honored verbatim (shape-gated).
        assert env.active_context(root=a) == "newsletter"

    def test_never_raises_and_defaults_empty(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CABINET_CONTEXT", raising=False)
        assert env.active_context(root=tmp_path / "missing") == ""
        assert env.active_context(officer="anyone",
                                  root=tmp_path / "missing",
                                  default="sentinel") == "sentinel"
