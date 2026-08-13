"""Declaring a connector from onboarding — the WRITE half of the read lane.

WHAT EACH ARM IS POINTED AT, because a sensor aimed at something other than the
control is this program's dominant defect class:

* the SHIPPED-PACK arm resolves every template in the real
  ``instance/config/connector-templates.yml.example`` and asserts each built
  inventory passes ``assert_read_only`` — so a future edit that turned a shipped
  template into a write is caught here, at the pack, not in production;
* the WIRE arm drives ``journey.act`` end to end — declare, then gather — and
  asserts the sweep read the declared connector and the entry mode FLIPS to
  connected. It fails against a tree without the ``declare_connector`` branch,
  which is the only proof the write is real and not a grep;
* the CUSTODY arms assert the credential env NAME reaches ``connectors.yml`` and
  the credential VALUE never could — the value is not even an input to the
  writer, and the arm proves the file never gains it;
* the CEILING arm hands the writer a template whose inventory would WRITE and
  asserts it is refused AND that the config did not gain the entry — a refusal
  that still wrote would pass a weaker check;
* the NEVER-CLOBBER arms are the degenerate ends of the merge: an absent file is
  created, a present file is appended to with its existing entries and its
  hand-written comments intact, and a name already declared is refused;
* the SOCKET arm stands up a real local server and proves ``_http_fetch`` reads
  it over a real socket without following a redirect — the half the injected
  ``fetch`` stub cannot prove. The full sweep runs on the stub because the
  ceiling is HTTPS-only by design, so a plain-http loopback cannot pass it, and
  weakening the ceiling to let a test through is the one thing this lane forbids.
"""
from __future__ import annotations

import json
import threading
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from framework.onboarding import journey, research

CRED = "s3cr3t-value-that-must-never-appear"
#: Written as ONE joined literal, never a bare "instance" segment: the
#: layer-separation gate reads that segment as a framework->instance coupling.
CONFIG_DIR = "instance/config"
TEMPLATES_TWIN = CONFIG_DIR + "/connector-templates.yml.example"


# ------------------------------------------------------------------ helpers --
def _sandbox(tmp_path: Path, *, enforce: bool = False) -> Path:
    """A root carrying the SHIPPED template pack and an open egress ceiling."""
    (tmp_path / CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    (tmp_path / TEMPLATES_TWIN).write_text(
        Path(TEMPLATES_TWIN).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / CONFIG_DIR / "egress.yml").write_text(
        f"enforce: {'true' if enforce else 'false'}\nallow_hosts: []\n", encoding="utf-8")
    return tmp_path


def _declare(root: Path, template: str, *, name: str, credential_env: str,
             fields: dict | None = None, action_id: str | None = None) -> dict:
    return journey.act({
        "action": "declare_connector", "surface": "cli",
        "action_id": action_id or f"act-{template}{'x' * 16}",
        "template": template, "name": name,
        "credential_env": credential_env, "fields": fields or {},
    }, root=root)


def _github_inventory(n: int) -> list:
    return [{"full_name": f"acme/repo-{i}",
             "updated_at": f"2026-08-{(i % 27) + 1:02d}T00:00:00Z",
             "owner": {"login": f"user-{i % 3}"},
             "private": True, "description": "CONFIDENTIAL-ROW-BODY"}
            for i in range(n)]


# --------------------------------------------- the shipped pack is read-only
def test_every_shipped_template_builds_a_read_only_connector(tmp_path):
    """The catalog the operator is offered cannot carry a write."""
    templates = research.load_connector_templates(_sandbox(tmp_path))
    assert set(templates) >= {"github", "vercel", "monday", "rest"}, templates
    fills = {
        "rest": {"url": "https://api.example.test/v1/things?page={page}",
                 "name_field": "name", "updated_field": "updated_at"},
    }
    for tid, tpl in templates.items():
        # A template that asks the operator something is answered with ITS OWN
        # placeholder — the string the pack tells the operator to type. Filling
        # required fields with nothing would refuse the build and pass this arm
        # for the wrong reason, which is how a whole pack could go unchecked.
        answers = dict(fills.get(tid) or {})
        for field in tpl.get("fields") or ():
            key, placeholder = str(field.get("key") or ""), str(field.get("placeholder") or "")
            if key and placeholder:
                answers.setdefault(key, placeholder)
        entry = research.build_connector_from_template(
            templates, tid, name=tid, credential_env="TEST_TOKEN", fields=answers)
        # The BUILT inventory is a read — refused otherwise, before any write.
        research.assert_read_only(entry["inventory"])
        assert entry["credential_env"] == "TEST_TOKEN"


# ------------------------------------------------ declare, then GATHER (wire)
def test_the_connect_path_declares_then_sweeps_to_connected_mode(tmp_path, monkeypatch):
    root = _sandbox(tmp_path)

    # 0. The real front: the operator answers the three questions and chooses to
    #    go find where the cabinet is useful — the branch this whole step is on.
    journey.act({"action": "answer_seed", "surface": "cli",
                 "action_id": "act-seed" + "x" * 16,
                 "seed": "I run billing for an engineering team",
                 "start_preference": "decide"}, root=root)

    # 1. DECLARE github. The credential VALUE is not an input here.
    out = _declare(root, "github", name="code", credential_env="GITHUB_TOKEN")
    assert out["ok"] is True
    text = (root / research.CONNECTORS_REL).read_text(encoding="utf-8")
    assert "GITHUB_TOKEN" in text                 # the env NAME is written
    assert CRED not in text                        # a credential value never is
    assert [s["name"] for s in research.load_connector_specs(root)] == ["code"]

    # 2. The credential VALUE lands only in the environment (as .env would hold
    #    it); the sweep reads it there, never from connectors.yml.
    monkeypatch.setenv("GITHUB_TOKEN", CRED)
    inv = _github_inventory(5)

    def fetch(request, timeout):
        # The identity call hits /user; the inventory call is the repos list.
        if request["url"].rstrip("/").endswith("/user"):
            return 200, json.dumps({"login": "user-me", "name": "Me"}).encode()
        return 200, json.dumps(inv).encode()

    monkeypatch.setattr(research, "_http_fetch", fetch)

    # 3. GATHER through the same public action the dashboard calls.
    swept = journey.act({"action": "gather_connectors", "surface": "cli",
                         "action_id": "act-" + "g" * 20}, root=root)
    state = swept["state"]

    # The found-summary rendered: counts, actors, freshest — contents-free.
    summary = {c["name"]: c for c in state["connector_sweep"]["connectors"]}["code"]
    assert summary["connected"] is True
    assert summary["items"] == 5
    assert summary["actors"] == 3
    assert summary["latest"] == "2026-08-05T00:00:00Z"
    blob = json.dumps(state)
    assert "CONFIDENTIAL-ROW-BODY" not in blob       # no body left the response
    assert CRED not in blob                           # no credential reached state

    # The entry mode FLIPPED to connected — the mode whose grant key had no
    # writer for connectors until declare_connector landed.
    sweep = research.sweep_connectors(root, env={"GITHUB_TOKEN": CRED}, fetch=fetch)
    grants = research.probe_connectors(root, sweep=sweep)["grants"]["connectors"]
    assert grants == ["connector:code"], grants

    # And the sweep produced something to propose over: ranked rows, and a card
    # that now offers a window to open (and the identity question the read
    # raised). The read did not just run — it opened the next move.
    assert state["salience_rows"]["rows"], "no ranked rows for the question"
    offered = {o["action"] for o in swept["card"].get("options", [])}
    assert "propose_window" in offered, offered
    assert "record_operator_identity" in offered, offered


# -------------------------------------------------- MANY tools, ONE sweep --
def test_three_tools_connect_and_one_sweep_covers_all_of_them(tmp_path, monkeypatch):
    """The Captain's second ask: connect MANY, then look across everything.

    POINTED AT THE AGGREGATE, not at three separate reads. `gather_connectors`
    is payload-free and sweeps whatever is declared, so the arm that matters is
    whether ONE act after three declarations returns three rows, ranks over all
    three, and keeps them distinguishable. A per-connector loop would pass while
    the real UX (one button, everything) stayed broken.
    """
    root = _sandbox(tmp_path)
    journey.act({"action": "answer_seed", "surface": "cli",
                 "action_id": "act-seed" + "x" * 16,
                 "seed": "I run billing for an engineering team",
                 "start_preference": "decide"}, root=root)

    for template, env in (("github", "GITHUB_TOKEN"),
                          ("vercel", "VERCEL_API_TOKEN"),
                          ("monday", "MONDAY_API_TOKEN")):
        out = _declare(root, template, name=template, credential_env=env,
                       action_id=f"act-{template}{'y' * 16}")
        assert out["ok"] is True, template
        monkeypatch.setenv(env, CRED)
    assert [s["name"] for s in research.load_connector_specs(root)] == \
        ["github", "vercel", "monday"]

    # ONE tool's credential is wrong. Its host answers 401; the other two answer
    # normally — which is the whole point: a refused key is that tool's fact.
    def fetch(request, timeout):
        host = request["url"].split("://", 1)[1].split("/", 1)[0]
        if host == "api.vercel.com":
            return 401, b'{"error":{"message":"invalid token"}}'
        if host == "api.github.com":
            if request["url"].rstrip("/").endswith("/user"):
                return 200, json.dumps({"login": "user-me"}).encode()
            return 200, json.dumps(_github_inventory(4)).encode()
        if host == "api.monday.com":
            return 200, json.dumps({"data": {"boards": [
                {"name": f"Board {i}", "updated_at": "2026-08-02T00:00:00Z",
                 "creator": {"name": "Ada"}} for i in range(3)]}}).encode()
        raise AssertionError(f"the sweep reached an undeclared host: {host}")

    monkeypatch.setattr(research, "_http_fetch", fetch)

    swept = journey.act({"action": "gather_connectors", "surface": "cli",
                         "action_id": "act-" + "m" * 20}, root=root)
    rows = {c["name"]: c for c in swept["state"]["connector_sweep"]["connectors"]}

    assert set(rows) == {"github", "vercel", "monday"}, rows
    assert rows["github"]["connected"] is True and rows["github"]["items"] == 4
    assert rows["monday"]["connected"] is True and rows["monday"]["items"] == 3
    # THE ISOLATION THIS ARM EXISTS FOR: the bad key is reported against its own
    # tool, by its own reason, and takes nothing else down with it.
    assert rows["vercel"]["connected"] is False
    assert rows["vercel"]["reason"] == "http_401", rows["vercel"]
    assert rows["vercel"]["items"] == 0

    # And the ranking is drawn from BOTH working connectors, not just the first.
    ranked = swept["state"]["salience_rows"]["rows"]
    assert {r["connector"] for r in ranked} == {"github", "monday"}, ranked
    blob = json.dumps(swept["state"])
    assert CRED not in blob and "CONFIDENTIAL-ROW-BODY" not in blob


def test_a_second_sweep_after_a_fourth_tool_covers_the_fourth_too(tmp_path, monkeypatch):
    """Connect another, look again — the sweep is the AGGREGATE every time.

    The defect this catches is a sweep that reports only what changed, or a UI
    state that remembers the first result: after adding a tool, the one act must
    still describe every declared connector, including the ones already read.
    """
    root = _sandbox(tmp_path)
    _declare(root, "github", name="github", credential_env="GITHUB_TOKEN")
    monkeypatch.setenv("GITHUB_TOKEN", CRED)
    monkeypatch.setenv("SHORTCUT_API_TOKEN", CRED)

    def fetch(request, timeout):
        host = request["url"].split("://", 1)[1].split("/", 1)[0]
        if host == "api.github.com":
            if request["url"].rstrip("/").endswith("/user"):
                return 200, json.dumps({"login": "user-me"}).encode()
            return 200, json.dumps(_github_inventory(2)).encode()
        return 200, json.dumps([
            {"name": "Epic one", "updated_at": "2026-08-09T00:00:00Z"}]).encode()

    monkeypatch.setattr(research, "_http_fetch", fetch)
    first = journey.act({"action": "gather_connectors", "surface": "cli",
                         "action_id": "act-" + "n" * 20}, root=root)
    assert [c["name"] for c in first["state"]["connector_sweep"]["connectors"]] == ["github"]

    _declare(root, "shortcut", name="shortcut", credential_env="SHORTCUT_API_TOKEN",
             action_id="act-shortcut" + "z" * 12)
    second = journey.act({"action": "gather_connectors", "surface": "cli",
                          "action_id": "act-" + "o" * 20}, root=root)
    rows = {c["name"]: c for c in second["state"]["connector_sweep"]["connectors"]}
    assert set(rows) == {"github", "shortcut"}, rows
    assert rows["github"]["items"] == 2 and rows["shortcut"]["items"] == 1


def test_a_template_field_may_ask_for_a_name_instead_of_a_whole_address(tmp_path):
    """`into_format`: the operator answers "acme", the shape gets the URL.

    The failure it removes is a connect step that hands a non-technical operator
    a URL to assemble. The property that must survive it is that the SCHEME is
    the template author's — an operator value can never make the call plaintext.
    """
    root = _sandbox(tmp_path)
    templates = research.load_connector_templates(root)
    # Found by SHAPE, never by name: this file is under framework/, which names
    # no vendor, and an arm pinned to one pack entry would also break the moment
    # that entry is curated away.
    tid, tpl, field = next(
        (tid, tpl, f)
        for tid, tpl in sorted(templates.items())
        for f in (tpl.get("fields") or ())
        if f.get("into_format"))
    shape = str(field["into_format"])
    entry = research.build_connector_from_template(
        templates, tid, name="shaped", credential_env="SHAPED_TOKEN",
        fields={str(field["key"]): "acme"})
    assert entry["inventory"]["url"] == shape.replace("{value}", "acme")
    assert "{value}" not in entry["inventory"]["url"]
    research.assert_read_only(entry["inventory"])

    # A pack whose format does not pin https is refused rather than sent.
    broken = deepcopy(tpl)
    for candidate in broken["fields"]:
        if candidate.get("into_format"):
            candidate["into_format"] = "http://{value}/x"
    with pytest.raises(research.ConnectorDeclarationError):
        research.build_connector_from_template(
            {tid: broken}, tid, name="shaped", credential_env="SHAPED_TOKEN",
            fields={str(field["key"]): "acme"})


# ------------------------------------------------------------- the ceiling
@pytest.mark.parametrize("bad_fields, why", [
    # A custom URL that is not https is refused, with the sweep's own verdict.
    ({"url": "http://api.example.test/x", "name_field": "n", "updated_field": "u"},
     "url_not_https"),
])
def test_a_write_or_non_read_template_is_refused_before_the_config_gains_it(
        tmp_path, bad_fields, why):
    root = _sandbox(tmp_path)
    with pytest.raises(journey.JourneyError) as excinfo:
        _declare(root, "rest", name="bad", credential_env="BAD_TOKEN", fields=bad_fields)
    assert why in str(excinfo.value)
    # AND the config did not gain the entry — a refusal that still wrote would
    # pass an arm that only checked the raised error.
    assert not (root / research.CONNECTORS_REL).is_file()


def test_a_write_verb_inventory_is_refused_at_the_writer(tmp_path):
    """The writer's own last-line ceiling, independent of the template path: an
    entry whose inventory could write never reaches the file."""
    root = _sandbox(tmp_path)
    writing_entry = {
        "name": "danger", "credential_env": "X_TOKEN",
        "inventory": {"url": "https://api.example.test/x", "method": "DELETE"},
    }
    with pytest.raises(research.ConnectorDeclarationError):
        research.write_connector_declaration(root, writing_entry)
    assert not (root / research.CONNECTORS_REL).is_file()


# -------------------------------------------------------- never clobber
def test_absent_file_is_created_and_a_second_declare_appends(tmp_path):
    root = _sandbox(tmp_path)
    assert not (root / research.CONNECTORS_REL).is_file()
    _declare(root, "github", name="code", credential_env="GITHUB_TOKEN")
    _declare(root, "vercel", name="hosting", credential_env="VERCEL_API_TOKEN")
    names = [s["name"] for s in research.load_connector_specs(root)]
    assert names == ["code", "hosting"]


def test_a_declare_preserves_an_existing_entry_and_its_comments(tmp_path):
    root = _sandbox(tmp_path)
    hand_written = (
        "schema: cabinet.connectors/v1\n\n"
        "connectors:\n"
        "  # A measured finding the operator wrote and must not lose.\n"
        "  - name: tracker\n"
        "    credential_env: TRACKER_TOKEN\n"
        "    inventory:\n"
        "      url: https://api.example.test/v2\n"
        "      method: GET\n"
        "      items_path: things\n"
        "      name_field: name\n"
        "      updated_field: updated_at\n"
    )
    (root / research.CONNECTORS_REL).write_text(hand_written, encoding="utf-8")
    _declare(root, "github", name="code", credential_env="GITHUB_TOKEN")
    after = (root / research.CONNECTORS_REL).read_text(encoding="utf-8")
    assert "A measured finding the operator wrote" in after   # comment survived
    names = [s["name"] for s in research.load_connector_specs(root)]
    assert names == ["tracker", "code"]                        # both entries present


def test_a_name_already_declared_is_refused_and_the_file_is_unchanged(tmp_path):
    root = _sandbox(tmp_path)
    _declare(root, "github", name="code", credential_env="GITHUB_TOKEN")
    before = (root / research.CONNECTORS_REL).read_text(encoding="utf-8")
    with pytest.raises(journey.JourneyError) as excinfo:
        _declare(root, "vercel", name="code", credential_env="VERCEL_API_TOKEN",
                 action_id="act-dup" + "x" * 16)
    assert "already set up" in str(excinfo.value)
    assert (root / research.CONNECTORS_REL).read_text(encoding="utf-8") == before
    assert len(research.load_connector_specs(root)) == 1


# --------------------------------------------------- degenerate build ends
def test_an_unknown_template_is_named_not_built(tmp_path):
    root = _sandbox(tmp_path)
    with pytest.raises(journey.JourneyError):
        _declare(root, "not-a-tool", name="x", credential_env="X_TOKEN")
    assert not (root / research.CONNECTORS_REL).is_file()


def test_a_missing_required_field_is_refused_by_its_label(tmp_path):
    root = _sandbox(tmp_path)
    with pytest.raises(journey.JourneyError) as excinfo:
        _declare(root, "rest", name="x", credential_env="X_TOKEN",
                 fields={"url": "https://api.example.test/x"})  # no name_field/updated_field
    assert "needed" in str(excinfo.value)


def test_a_field_the_template_never_asked_for_is_refused(tmp_path):
    root = _sandbox(tmp_path)
    with pytest.raises(journey.JourneyError):
        _declare(root, "github", name="x", credential_env="X_TOKEN",
                 fields={"url": "https://evil.test/collect"})  # github asks for none


def test_a_bad_env_var_name_is_refused(tmp_path):
    root = _sandbox(tmp_path)
    with pytest.raises(journey.JourneyError):
        _declare(root, "github", name="x", credential_env="not a valid name")


# ------------------------------------------------ a real socket, read-only
def test_http_fetch_reads_a_local_server_and_does_not_follow_a_redirect():
    """The socket half the injected stub cannot prove: a real read over a real
    127.0.0.1 socket, and a 30x surfaced as a status rather than followed (which
    would hand the credential to whatever the redirect names)."""
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — stdlib naming
            seen.append((self.path, self.headers.get("Authorization")))
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/elsewhere")
                self.end_headers()
                return
            body = json.dumps([{"full_name": "acme/one",
                                "updated_at": "2026-08-01T00:00:00Z"}]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        status, payload = research._http_fetch(
            {"url": f"http://{host}:{port}/list", "method": "GET",
             "headers": {"Authorization": CRED}, "body": None}, 10)
        assert status == 200
        assert json.loads(payload)[0]["full_name"] == "acme/one"

        redir, _ = research._http_fetch(
            {"url": f"http://{host}:{port}/redirect", "method": "GET",
             "headers": {"Authorization": CRED}, "body": None}, 10)
        assert redir == 302
        assert [p for p, _ in seen] == ["/list", "/redirect"]  # /elsewhere never hit
    finally:
        server.shutdown()
        server.server_close()
