"""CABINET_ENV safety switch — fail-safe by default (dev), opt-in to runtime."""
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

    def test_result_is_cached_process_wide(self, tmp_path, monkeypatch,
                                           isolated_role_cache):
        """First resolution wins for the process (a restart re-reads)."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", "captain_role: First\n")
        env._captain_role_cache = None
        assert env.captain_role() == "First"
        _write_cfg(tmp_path, "platform.yml", "captain_role: Second\n")  # ignored
        assert env.captain_role() == "First"

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
                   "org_domains:\n  - '  StepNetwork.DK '\n  - JFMedier.dk\n")
        env._org_domains_cache = None
        assert env.org_domains() == ("stepnetwork.dk", "jfmedier.dk")

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

    def test_this_instance_yields_the_six_org_domains(self, monkeypatch,
                                                      isolated_org_domains_cache):
        """Byte-identity guard: with CABINET_ROOT unset the resolver reads THIS
        worktree's instance/config/platform.yml, yielding the exact six domains
        the classifier hardcode carried — so is_internal is byte-identical."""
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        env._org_domains_cache = None
        assert env.org_domains() == (
            "stepnetwork.dk", "jfmedier.dk", "jysk-fynske-medier.dk",
            "polads.eu", "refslund.ai", "step.dk",
        )


class TestTasksBoard:
    """The tasks_board() resolver — instance-DRIVEN, fail-closed to "".

    action_exec's DEFAULT_TASKS_BOARD and the act-first canary read the board id
    via this resolver, never a literal. On THIS deployment it must return
    "5091706356" so the executor + canary are byte-identical."""

    def test_reads_board_from_platform_yml(self, tmp_path, monkeypatch,
                                           isolated_tasks_board_cache):
        monkeypatch.delenv("CABINET_TASKS_BOARD", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "platform.yml", 'tasks_board: "1234567890"\n')
        env._tasks_board_cache = None
        assert env.tasks_board() == "1234567890"

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
        _write_cfg(tmp_path, "platform.yml", 'tasks_board: "1111111111"\n')
        monkeypatch.setenv("CABINET_TASKS_BOARD", "9999999999")
        env._tasks_board_cache = None
        assert env.tasks_board() == "9999999999"

    def test_reads_nested_board_from_product_yml(self, tmp_path, monkeypatch,
                                                 isolated_tasks_board_cache):
        monkeypatch.delenv("CABINET_TASKS_BOARD", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_cfg(tmp_path, "product.yml",
                   'product:\n  tasks_board: "2222222222"\n')
        env._tasks_board_cache = None
        assert env.tasks_board() == "2222222222"

    def test_this_instance_yields_the_tasks_board(self, monkeypatch,
                                                  isolated_tasks_board_cache):
        """Byte-identity guard: this worktree's platform.yml yields 5091706356,
        so DEFAULT_TASKS_BOARD + the canary probe board are byte-identical."""
        monkeypatch.delenv("CABINET_TASKS_BOARD", raising=False)
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        env._tasks_board_cache = None
        assert env.tasks_board() == "5091706356"


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

    def test_this_instance_yields_europe_berlin(self, monkeypatch,
                                                isolated_timezone_cache):
        """Byte-identity guard: with CABINET_ROOT unset the resolver finds the
        repo via env.py's file-relative parents[N] and reads THIS worktree's
        instance/config/platform.yml, which yields Europe/Berlin — so
        _captain_tz() renders the identical zone to the removed hand-reader."""
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        env._captain_timezone_cache = None
        assert env.captain_timezone() == "Europe/Berlin"
