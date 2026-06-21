"""CABINET_ENV safety switch — fail-safe by default (dev), opt-in to runtime."""
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
