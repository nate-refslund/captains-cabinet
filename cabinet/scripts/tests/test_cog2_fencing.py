"""COG-2 UNIT 4 — cross-cabinet + boundary fence gate (§8 sim 7, tests-first).

The mechanical proof that a cross-cabinet envelope is QUARANTINED at ingest
(never folded into the local projection) and that a cross-cabinet / foreign /
unresolvable-scope query fails CLOSED with a HARD ERROR (ScopeError) — never an
empty-success that lets an attacker distinguish "denied" from "no data" by the
emptiness of the answer.

Two fences, two surfaces (§7.4 / C-F19):

  * INGEST (framework.cortex.adapters._envelope_scope_reason): a fail-closed
    scope check on a validate_any-passing v2 envelope. It OWNS three refusals so
    a cross-cabinet envelope never reaches the fold:
      - classification == "cross_cabinet" — a VALID taint tier (envelope
        .TAINT_TIERS = captain/officer/system/cross_cabinet/external) that PASSES
        validate_any, so the validator never stops it; a cross_cabinet envelope
        carrying a LOCAL cabinet_id would otherwise FOLD (the pinned leak). The
        fence refuses it REGARDLESS of cabinet_id.
      - absent cabinet_id — absent is never local, fail closed.
      - foreign cabinet_id — not the local cabinet.
    Every refusal writes a QUARANTINE RECEIPT; a silent skip is itself a pinned
    mutant failure (a silent drop is an undetected loss).

  * QUERY (framework.cortex.query.as_of scope gate, unit 2): a missing /
    unresolvable / foreign scope is a HARD ERROR (ScopeError), never
    empty-success; a scoped query over a mixed local+foreign store leaks NO
    foreign belief (in_scope filters on provenance.cabinet_id).

Negative controls (MUST fail):
  * a cross_cabinet-classified envelope FOLDED (a proto produced) instead of
    quarantined — the fence gap this unit closes (pinned by the direct
    _envelope_scope_reason unit test AND the ingest quarantine assertions).
  * quarantine-WITHOUT-a-receipt / a silently-skipped refused line.
  * the cross_cabinet refusal rejecting a NORMAL local system-classification
    envelope (over-fencing — would break unit 2/3; pinned by the allow tests).
  * an empty-success query fence (empty views, no error) instead of a hard
    ScopeError — the documented scope_mode="lenient" mutant seam; an attacker
    must not read denial as ignorance.

S0: interpreter python3.12. No DB — the envelope-file adapter reads a JSONL and
the query folds an in-memory belief list (the sim-3 discipline).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
for _p in (str(_HERE), _ROOT):          # tests/ is a package: put it on the path
    if _p not in sys.path:
        sys.path.insert(0, _p)

from framework.cortex import adapters, engine, query  # noqa: E402
from framework.triggers import envelope as _envelope  # noqa: E402
import lib_cog2_envelope as L  # noqa: E402

TT = L.TRUST_TABLE
MAIN = {"cabinet_id": "main"}
S1 = "2026-07-20T00:00:00Z"
O1 = "2026-07-20T01:00:00Z"


# ---------------------------------------------------------------------------
# helpers — build a JSONL the PRODUCTION adapter reads read-only (no test seam)
# ---------------------------------------------------------------------------

def _ingest(tmp_path, envs, *, local="main", name="fence.jsonl"):
    """(protos, receipts) straight from the production read_envelope_file path —
    NOT asserting a clean run (sim 7 WANTS the quarantines)."""
    path = L.write_jsonl(tmp_path / name, envs)
    return adapters.read_envelope_file(path, local_cabinet_id=local)


def _fold_local(tmp_path, envs, *, local, name):
    """Fold envelopes that ARE local to `local` into a belief list (asserts a
    clean ingest — used to seed a store, never to test the fence)."""
    protos, receipts = _ingest(tmp_path, envs, local=local, name=name)
    assert receipts == [], f"unexpected quarantine seeding {local}: {receipts}"
    return engine.fold(protos, trust_table=TT)


def _local_env(**kw):
    kw.setdefault("seed", 1)
    kw.setdefault("producer", L.PRIMARY)
    kw.setdefault("subject", "widget-1")
    kw.setdefault("state", "hot")
    kw.setdefault("occurred_at", S1)
    kw.setdefault("recorded_at", O1)
    return L.envelope(**kw)


# ===========================================================================
# INGEST fence — foreign / cross_cabinet / sentinel each quarantined WITH a
# receipt, never a proto (§7.4; silent skip = failure)
# ===========================================================================

class TestIngestQuarantine:
    def test_foreign_cabinet_id_quarantined_with_receipt(self, tmp_path):
        env = _local_env(seed=10, cabinet_id="other-cabinet")
        protos, receipts = _ingest(tmp_path, [env])
        assert protos == []                              # never folded
        assert len(receipts) == 1
        assert "foreign" in receipts[0]["reason"]
        assert receipts[0]["event_id"] == env["event_id"]   # receipt carries identity

    def test_cross_cabinet_classification_quarantined_even_with_local_id(self, tmp_path):
        # THE PINNED GAP: classification cross_cabinet is a VALID taint tier that
        # PASSES validate_any, and the cabinet_id is LOCAL — so the ONLY thing
        # that can stop it folding is the adapter's own classification fence.
        env = _local_env(seed=11, cabinet_id="main", classification="cross_cabinet")
        ok, reasons = _envelope.validate_any(env)
        assert ok, f"fixture must be a VALID-tier envelope the validator passes: {reasons}"
        protos, receipts = _ingest(tmp_path, [env])
        assert protos == []                              # NOT folded (mutant would fold)
        assert len(receipts) == 1
        assert "cross_cabinet" in receipts[0]["reason"]
        assert receipts[0]["event_id"] == env["event_id"]

    def test_sentinel_scope_id_quarantined_with_receipt(self, tmp_path):
        # a sentinel cabinet_id ("*") is refused by validate_any (V2_SENTINEL_IDS)
        # — still a QUARANTINE WITH A RECEIPT, never a silent drop.
        env = _local_env(seed=12, cabinet_id="*")
        protos, receipts = _ingest(tmp_path, [env])
        assert protos == []
        assert len(receipts) == 1
        assert "sentinel" in receipts[0]["reason"]

    def test_absent_cabinet_id_fails_closed_with_receipt(self, tmp_path):
        # absent cabinet_id (never local) — validate_any flags the missing
        # required key; the line is quarantined, never folded as-local.
        env = _local_env(seed=13)
        env.pop("cabinet_id")
        protos, receipts = _ingest(tmp_path, [env])
        assert protos == []
        assert len(receipts) == 1

    def test_every_refused_line_has_a_receipt_never_silent_skip(self, tmp_path):
        # a mixed file: 2 GOOD local lines + 3 BAD (foreign / cross_cabinet /
        # sentinel). Exactly the 2 good fold; exactly the 3 bad get receipts.
        # Pins BOTH "quarantine-without-receipt" and "silent skip" mutants.
        envs = [
            _local_env(seed=20, subject="ok-a"),
            _local_env(seed=21, cabinet_id="foreign"),
            _local_env(seed=22, classification="cross_cabinet"),
            _local_env(seed=23, cabinet_id="null"),          # sentinel
            _local_env(seed=24, subject="ok-b"),
        ]
        protos, receipts = _ingest(tmp_path, envs)
        assert len(protos) == 2                          # only the 2 good
        assert {p["subject_key"] for p in protos} == {
            "observations/ok-a", "observations/ok-b"}
        assert len(receipts) == 3                         # every bad line -> a receipt
        # accounting is exact: goods + bads == total lines (no silent skip)
        assert len(protos) + len(receipts) == len(envs)


# ===========================================================================
# INGEST fence — the COMPLETE standalone _envelope_scope_reason contract
# (a validated envelope need not have run through validate_any first)
# ===========================================================================

class TestScopeReasonUnit:
    def test_cross_cabinet_refused_even_with_local_cabinet_id(self):
        # the exact mutant-kill: a LOCAL cabinet_id + cross_cabinet class must
        # return a REFUSAL. The pre-fix fence returned None here (would fold).
        reason = adapters._envelope_scope_reason(
            {"classification": "cross_cabinet", "cabinet_id": "main"},
            local_cabinet_id="main")
        assert reason is not None
        assert "cross_cabinet" in reason

    def test_cross_cabinet_refused_regardless_of_cabinet_id(self):
        # cross_cabinet + a foreign cabinet_id is still refused (either axis).
        reason = adapters._envelope_scope_reason(
            {"classification": "cross_cabinet", "cabinet_id": "elsewhere"},
            local_cabinet_id="main")
        assert reason is not None

    def test_local_system_classification_is_allowed(self):
        # NO OVER-FENCING: a normal local system envelope folds (None) — the
        # cross_cabinet refusal must not reject unit 2/3's real local streams.
        assert adapters._envelope_scope_reason(
            {"classification": "system", "cabinet_id": "main"},
            local_cabinet_id="main") is None

    @pytest.mark.parametrize("cls", ["system", "officer", "captain", "external"])
    def test_non_cross_cabinet_local_classifications_allowed(self, cls):
        # ONLY cross_cabinet is fenced by classification; the other four taint
        # tiers on a LOCAL cabinet_id fold (external taint is a different concern
        # — it is NOT a cross-cabinet marker, so it is not refused here).
        assert adapters._envelope_scope_reason(
            {"classification": cls, "cabinet_id": "main"},
            local_cabinet_id="main") is None

    def test_foreign_cabinet_id_refused(self):
        reason = adapters._envelope_scope_reason(
            {"classification": "system", "cabinet_id": "other"},
            local_cabinet_id="main")
        assert reason is not None
        assert "foreign" in reason

    def test_absent_cabinet_id_fails_closed(self):
        reason = adapters._envelope_scope_reason(
            {"classification": "system"}, local_cabinet_id="main")
        assert reason is not None
        assert "absent" in reason


# ===========================================================================
# QUERY fence — HARD ERROR, never empty-success (§7.4, denial != ignorance)
# ===========================================================================

class TestQueryFailsClosed:
    def _local_store(self, tmp_path):
        return _fold_local(tmp_path, [_local_env(seed=30)],
                           local="main", name="q-local.jsonl")

    def test_foreign_scope_is_a_hard_error(self, tmp_path):
        beliefs = self._local_store(tmp_path)
        with pytest.raises(query.ScopeError):
            query.as_of(beliefs, "observations/widget-1",
                        scope={"cabinet_id": "some-other-cabinet"})

    def test_sentinel_scope_is_a_hard_error(self, tmp_path):
        beliefs = self._local_store(tmp_path)
        with pytest.raises(query.ScopeError):
            query.as_of(beliefs, "observations/widget-1",
                        scope={"cabinet_id": "*"})            # sentinel scope id

    def test_missing_scope_is_a_hard_error(self, tmp_path):
        beliefs = self._local_store(tmp_path)
        with pytest.raises(query.ScopeError):
            query.as_of(beliefs, "observations/widget-1", scope=None)

    def test_empty_success_mutant_bites(self, tmp_path):
        # MUTANT (scope_mode="lenient"): a foreign scope returns an empty-success
        # unknown instead of raising — denial masquerading as ignorance. This is
        # EXACTLY the shape the strict fence forbids: were the fence to return
        # empty-success, the strict ScopeError assertions above would not hold and
        # an attacker could not distinguish "denied" from "no data".
        beliefs = self._local_store(tmp_path)
        r = query.as_of(beliefs, "observations/widget-1",
                        scope={"cabinet_id": "some-other-cabinet"},
                        scope_mode="lenient")
        assert r.is_unknown()                            # the mutant's tell
        assert r.views == ()                             # empty-success (no error)


# ===========================================================================
# QUERY fence — a scoped query over a MIXED local+foreign store leaks NO
# foreign belief (C-F19 / IDOR-shaped cross-cabinet read)
# ===========================================================================

class TestScopedQueryNoForeignLeak:
    def _mixed_store(self, tmp_path):
        # SAME subject_key present in two cabinets: a local "main" belief and a
        # foreign "other" belief carrying a sentinel-obvious secret state. Each is
        # local to ITS OWN fold, so both fold cleanly; the query scope must
        # isolate them. Distinct seeds => distinct event_ids => distinct
        # belief_ids (no collapse), same subject "widget-1".
        main = _fold_local(
            tmp_path,
            [_local_env(seed=101, subject="widget-1", state="local-truth")],
            local="main", name="mix-main.jsonl")
        other = _fold_local(
            tmp_path,
            [_local_env(seed=202, subject="widget-1", state="FOREIGN-SECRET",
                        cabinet_id="other")],
            local="other", name="mix-other.jsonl")
        return list(main) + list(other), main, other

    def test_local_scope_returns_only_local_belief(self, tmp_path):
        store, main, other = self._mixed_store(tmp_path)
        r = query.as_of(store, "observations/widget-1", scope=MAIN)
        assert not r.is_unknown()
        assert len(r.views) >= 1
        # every returned view is local; no foreign cabinet_id, no secret state
        for v in r.views:
            assert v.provenance.get("cabinet_id") == "main"
            assert (v.value or {}).get("state") != "FOREIGN-SECRET"
        # the foreign belief is nowhere in the fenced evidence set either
        foreign_ids = {b.belief_id for b in other}
        assert not (r.evidence_ids & foreign_ids)
        # sanity: the local belief IS the one served
        assert r.evidence_ids == {main[0].belief_id}

    def test_third_cabinet_scope_over_mixed_store_hard_errors(self, tmp_path):
        # the subject exists (in main AND other) but NOT in "third" — a
        # cross-cabinet mismatch is a HARD ERROR, never a silent unknown that
        # would leak the subject's cross-cabinet existence as ignorance.
        store, _main, _other = self._mixed_store(tmp_path)
        with pytest.raises(query.ScopeError):
            query.as_of(store, "observations/widget-1",
                        scope={"cabinet_id": "third"})


# ===========================================================================
# §7.2 read-only-by-construction cortex_ro role (G-F6) — the MISSING control.
#
# The §7.2 contract mandates a `cortex_ro` DB role: SELECT-only, grant list
# ENUMERATED and minimal (officer_tasks_outbox, officer_tasks — nothing else),
# provisioned by `cog2-rebuild.py --provision-ro` (idempotent SQL run by
# harness/CI). This suite is the mechanical proof, against a REAL ephemeral
# PG17 outbox:
#   * SELECT on both enumerated tables SUCCEEDS as cortex_ro;
#   * UPDATE and INSERT on both tables are REFUSED (42501 insufficient_privilege
#     — both verbs, both tables where a write would matter);
#   * the grant catalog matches the enumerated list EXACTLY — a THIRD-table
#     grant OR any write grant makes the catalog assertion FAIL (the mutant the
#     §7.2 catalog check exists to catch), and has_table_privilege corroborates
#     zero EFFECTIVE privilege on any other table (covers PUBLIC/inheritance,
#     not just direct grants);
#   * --provision-ro is idempotent — a second run succeeds (no duplicate-role
#     error) and the catalog is unchanged.
#
# Bootstrap mirrors the rebuild-determinism PG gate: start -> apply_base_chain
# -> apply_identity_guc -> apply_047, then provision via the CLI subprocess (the
# "run by harness/CI" contract). Skips without a PG17 toolchain + psycopg2.
#
# AUTH-AGNOSTIC by construction: the privilege tests NEVER open a cortex_ro
# LOGIN. cortex_ro is provisioned with LOGIN but no password (§7.2: the
# deployment supplies auth out-of-band), so a passwordless login only works on
# the local trust-auth cluster and FAILS on CI's password-auth server. Instead
# the role's privileges are exercised via `SET ROLE cortex_ro` on the ADMIN
# (superuser) connection — a POST-login switch that is authenticated regardless
# of auth method, and under which the superuser sheds its bypass so cortex_ro's
# real SELECT-only grants are enforced. Catalog/attribute facts read as admin
# (role_table_grants, has_table_privilege, pg_roles). No test does a live
# cortex_ro connection.
# ===========================================================================

import importlib.util as _ilu  # noqa: E402
import os as _os  # noqa: E402
import subprocess as _subprocess  # noqa: E402


def _load_mod(path, name):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


# the relay harness re-exports EphemeralPG17 + pg_available (the DB-plane idiom,
# loaded by path exactly as test_cog2_rebuild_determinism.py does).
_HR = _load_mod(_ROOT + "/framework/outbox/tests/lib_relay_harness.py",
                "lib_relay_harness_cog2fence")
_REBUILD = _HERE.parent / "cog2-rebuild.py"
_PG_SKIP = pytest.mark.skipif(not _HR.pg_available(), reason=_HR.PG_SKIP_REASON)
_FORBIDDEN = set(_HR.H.FORBIDDEN_CHILD_ENV)

_RO_TABLES = {"officer_tasks_outbox", "officer_tasks"}
_ENUM_CATALOG = {(t, "SELECT") for t in _RO_TABLES}   # the §7.2 enumerated set


def _child_env():
    """A DB/redis-var-stripped child env (the determinism-suite discipline): the
    provisioning subprocess can never inherit a live-store DSN."""
    env = {k: v for k, v in _os.environ.items() if k not in _FORBIDDEN}
    env.pop("COG2_OUTBOX_DSN", None)
    return env


def _provision_ro(dsn):
    """The MANDATED provisioning path — cog2-rebuild.py --provision-ro as a
    subprocess ("run by harness/CI"). Asserts a clean exit; returns the proc."""
    r = _subprocess.run(
        ["python3.12", str(_REBUILD), "--provision-ro", "--dsn", dsn],
        capture_output=True, text=True, env=_child_env())
    assert r.returncode == 0, f"provision-ro rc={r.returncode}\n{r.stderr}"
    return r


def _expect_denied_as_ro(cluster, sql):
    """Assert `sql` is REFUSED with SQLSTATE 42501 (insufficient_privilege) when
    run AS cortex_ro — via SET ROLE on an autocommit ADMIN (superuser) connection,
    never a cortex_ro LOGIN. This is the auth-agnostic core of the rewrite: SET
    ROLE is a POST-login switch, so it can NEVER raise a login/password-auth FATAL
    (the exact CI failure — cortex_ro has LOGIN but no password, and CI's server
    is password-auth). A superuser sheds its privilege bypass under SET ROLE, so
    cortex_ro's REAL grants are what gets enforced. Autocommit means the denied
    statement does not poison a follow-on statement (no aborted-txn block)."""
    import psycopg2  # lazy — collection must not require the driver
    conn = psycopg2.connect(cluster.conninfo())   # admin dsn — always authenticated
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SET ROLE cortex_ro")
            try:
                cur.execute(sql)
            except psycopg2.Error as exc:
                assert exc.pgcode == "42501", (
                    f"expected 42501 insufficient_privilege, got {exc.pgcode}: {exc}")
            else:
                raise AssertionError(f"write was NOT refused under cortex_ro: {sql}")
            cur.execute("RESET ROLE")   # post-login switch back (conn discarded next)
    finally:
        conn.close()


def _catalog(cluster):
    """The cortex_ro TABLE-grant catalog as a {(table, privilege)} set, read as
    the admin (the grantor sees role_table_grants). This IS the §7.2 catalog the
    enumerated list must match EXACTLY."""
    out = cluster.psql(
        "SELECT table_name, privilege_type "
        "FROM information_schema.role_table_grants "
        "WHERE grantee = 'cortex_ro' ORDER BY table_name, privilege_type;").stdout
    rows = set()
    for line in out.splitlines():
        line = line.strip()
        if line:
            table, priv = line.split("|", 1)
            rows.add((table, priv))
    return rows


@_PG_SKIP
class TestCortexRoReadOnly:
    """§7.2 / G-F6: the read-only-by-construction cortex_ro role."""

    @pytest.fixture(scope="class")
    def cluster(self, tmp_path_factory):
        c = _HR.EphemeralPG17(tmp_path_factory.mktemp("cog2rofence"),
                              cabinet_id=_HR.CAB_ID)
        try:
            c.start()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"could not start ephemeral PG17: {exc}")
        try:
            c.apply_base_chain()              # officer_tasks (+ officer_task_history)
            c.apply_identity_guc(_HR.CAB_ID)
            c.apply_047()                     # officer_tasks_outbox
            _provision_ro(c.conninfo())       # the ADMIN dsn -> cortex_ro
            yield c
        finally:
            c.stop()

    # -- SELECT on the two enumerated tables SUCCEEDS as cortex_ro ---------

    def test_select_on_enumerated_tables_succeeds(self, cluster):
        # AUTH-AGNOSTIC: exercise cortex_ro's privileges via SET ROLE on an admin
        # (superuser) connection — NO cortex_ro LOGIN is opened, so the cluster's
        # auth method (trust locally, PASSWORD in CI) is irrelevant. SET ROLE is a
        # post-login switch applying cortex_ro's SELECT grants exactly; the
        # superuser sheds its bypass under SET ROLE, so a real grant is required.
        import psycopg2
        conn = psycopg2.connect(cluster.conninfo())   # admin dsn — always authed
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute("SET ROLE cortex_ro")
                for table in sorted(_RO_TABLES):
                    cur.execute(f"SELECT count(*) FROM {table}")
                    assert cur.fetchone()[0] is not None
                cur.execute("RESET ROLE")
        finally:
            conn.close()

    # -- UPDATE + INSERT on both tables are REFUSED (42501) ---------------

    @pytest.mark.parametrize("sql", [
        "UPDATE officer_tasks_outbox SET attempts = attempts + 1",
        "INSERT INTO officer_tasks_outbox (idempotency_key, task_id, new_status, "
        "actor) VALUES ('ro-probe', 1, 'wip', 'ro')",
        "UPDATE officer_tasks SET title = title",
        "INSERT INTO officer_tasks (officer_slug, title, status) "
        "VALUES ('ro', 'ro-probe', 'queue')",
    ])
    def test_writes_are_refused(self, cluster, sql):
        # both verbs (UPDATE + INSERT), both tables where a write would matter —
        # each refused with insufficient_privilege, never silently accepted.
        # Assumed via SET ROLE on the admin conn (no cortex_ro login) — see
        # _expect_denied_as_ro; SET ROLE can never raise a login-auth error.
        _expect_denied_as_ro(cluster, sql)

    # -- the grant catalog matches the enumerated list EXACTLY ------------

    def test_grant_catalog_is_exactly_enumerated(self, cluster):
        # the mutant this exists to catch: a THIRD-table grant or a write grant
        # would make this set differ from the enumerated {SELECT x2}. The
        # catalog-bite proof (test_catalog_bite_proof_injected_grant_then_reconverge
        # below) drives this exact comparison with an injected grant in-repo.
        catalog = _catalog(cluster)
        assert catalog == _ENUM_CATALOG, (
            f"cortex_ro catalog {sorted(catalog)} != "
            f"enumerated {sorted(_ENUM_CATALOG)}")

    def test_catalog_bite_proof_injected_grant_then_reconverge(self, cluster):
        # CATALOG-BITE PROOF (in-repo, was transcript-only): the grant-catalog
        # comparison in test_grant_catalog_is_exactly_enumerated must actually
        # BITE on BOTH axes when the enumerated set is violated — a THIRD-table
        # grant and a WRITE-verb grant — and the idempotent provisioner must
        # CONVERGE the catalog back. Injections run as the admin (the grantor);
        # the finally re-provision keeps the class-scoped role clean for the other
        # tests even if an assertion fails.
        try:
            # (a) third-table axis: SELECT on a table NOT in the enumerated set.
            cluster.psql("GRANT SELECT ON officer_task_history TO cortex_ro;")
            bitten_a = _catalog(cluster)
            assert bitten_a != _ENUM_CATALOG, \
                "the catalog comparison must BITE on an injected third-table grant"
            assert ("officer_task_history", "SELECT") in bitten_a
            # (b) write-verb axis: INSERT on an ENUMERATED table.
            cluster.psql("GRANT INSERT ON officer_tasks_outbox TO cortex_ro;")
            bitten_b = _catalog(cluster)
            assert bitten_b != _ENUM_CATALOG, \
                "the catalog comparison must BITE on an injected write-verb grant"
            assert ("officer_tasks_outbox", "INSERT") in bitten_b
        finally:
            # REVOKE / re-provision: the provisioner REVOKEs ALL then re-grants
            # only the enumerated SELECTs, so the catalog CONVERGES back exactly —
            # the drift self-correction the §7.2 provisioning contract promises.
            _provision_ro(cluster.conninfo())
        assert _catalog(cluster) == _ENUM_CATALOG, \
            "re-provision must converge the catalog back to the enumerated set"
        # the injected INSERT grant is gone — cortex_ro is SELECT-only again.
        # Corroborated via admin has_table_privilege (covers direct grants +
        # PUBLIC + inheritance); no cortex_ro login needed, so it stays
        # auth-agnostic like the rest of the catalog assertions.
        assert cluster.one(
            "SELECT has_table_privilege('cortex_ro', 'officer_tasks_outbox', "
            "'INSERT');") == "f", \
            "re-provision must strip the injected INSERT grant (SELECT-only again)"

    def test_no_write_privilege_on_granted_tables(self, cluster):
        # has_table_privilege corroborates the catalog on the two GRANTED tables:
        # SELECT yes, every write verb no.
        for table in sorted(_RO_TABLES):
            assert cluster.one(
                f"SELECT has_table_privilege('cortex_ro', '{table}', 'SELECT');"
            ) == "t"
            for verb in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                assert cluster.one(
                    f"SELECT has_table_privilege('cortex_ro', '{table}', '{verb}');"
                ) == "f", f"cortex_ro must NOT have {verb} on {table}"

    def test_no_privilege_on_any_other_table(self, cluster):
        # a THIRD table (officer_task_history, minted by 038) — cortex_ro has NO
        # effective privilege on it (has_table_privilege covers PUBLIC + role
        # inheritance, not just direct grants), and it is absent from the direct
        # grant catalog entirely.
        assert cluster.one(
            "SELECT has_table_privilege('cortex_ro', 'officer_task_history', "
            "'SELECT');") == "f"
        assert "officer_task_history" not in {t for (t, _p) in _catalog(cluster)}

    def test_role_is_a_plain_login_not_privileged(self, cluster):
        # §7.2: LOGIN, and NO other attribute — never superuser/createdb/
        # createrole (a privileged role would defeat read-only-by-construction).
        # This proves the LOGIN guarantee WITHOUT a live login: pg_roles read as
        # admin shows cortex_ro CAN log in (rolcanlogin) and is otherwise a plain,
        # non-privileged role. Whether a live cortex_ro connection actually
        # authenticates is a DEPLOYMENT/auth concern — the deployment supplies the
        # credential/pg_hba out-of-band (§7.2) — and is out of this suite's scope.
        # The suite proves the role EXISTS with LOGIN and is SELECT-only, which is
        # exactly what read-only-by-construction requires.
        attrs = cluster.one(
            "SELECT rolcanlogin::text || ',' || rolsuper::text || ',' || "
            "rolcreatedb::text || ',' || rolcreaterole::text || ',' || "
            "rolinherit::text FROM pg_roles WHERE rolname = 'cortex_ro';")
        # rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit
        assert attrs == "true,false,false,false,false", attrs

    # -- idempotency: a second provision succeeds, catalog unchanged ------

    def test_provision_ro_is_idempotent(self, cluster):
        before = _catalog(cluster)
        assert before == _ENUM_CATALOG            # (sanity — first provision held)
        r = _provision_ro(cluster.conninfo())     # SECOND run: no duplicate-role error
        assert r.returncode == 0
        assert _catalog(cluster) == before == _ENUM_CATALOG
        # and it is STILL SELECT-only after the re-provision — admin
        # has_table_privilege (no cortex_ro login needed): SELECT yes, INSERT no.
        assert cluster.one(
            "SELECT has_table_privilege('cortex_ro', 'officer_tasks_outbox', "
            "'SELECT');") == "t"
        assert cluster.one(
            "SELECT has_table_privilege('cortex_ro', 'officer_tasks_outbox', "
            "'INSERT');") == "f"
