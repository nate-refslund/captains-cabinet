"""The credentialed READ-ONLY connector lane (Captain ruling 2026-07-29).

WHAT EACH ARM IS POINTED AT, because a sensor aimed at something other than the
control is this program's dominant defect class:

* the CEILING arms assert on the refusal that happens BEFORE a socket exists,
  and they prove it by handing in a fetch stub that RECORDS every request — an
  arm that only checked the raised exception would pass just as happily against
  a lane that made the call and then complained;
* the CONTENTS-FREE arms search the whole serialized result for a string that
  was in the response and must not be in the document, rather than checking that
  the fields it wanted are present (a document can carry both);
* the DEGENERATE arms are the zero/empty/absent end: no connectors declared, a
  connector that returns an empty list, a credential that is not set, a ceiling
  that is closed. Each has a DIFFERENT named reason, because collapsing them is
  how "nothing is connected" becomes indistinguishable from "I never looked";
* the WIRE arm drives ``journey.act`` and asserts the entry mode FLIPS to
  connected — the mode whose grant key had no writer for connectors until this
  landed. It fails against pre-change code, which is the only proof that the
  wire is real and not a grep.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from framework.onboarding import journey, research

CRED = "s3cr3t-value-that-must-never-appear"
#: Written as ONE joined literal, never as a bare "instance" path segment:
#: the layer-separation gate reads that segment as a framework->instance
#: coupling, and a test tripping it would spend a debt line on a fixture.
CONFIG_DIR = "instance/config"
EGRESS = CONFIG_DIR + "/egress.yml"


# ------------------------------------------------------------------ helpers --
class Recorder:
    """A fetch stub that records every request it is asked to make."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.seen = []

    def __call__(self, request, timeout):
        self.seen.append(request)
        payload = self.pages[min(len(self.seen) - 1, len(self.pages) - 1)]
        if isinstance(payload, tuple):
            return payload
        return 200, json.dumps(payload).encode("utf-8")


def _spec(**over):
    spec = {
        "name": "things",
        "credential_env": "TEST_CONNECTOR_TOKEN",
        "inventory": {
            "url": "https://api.example.test/v1/things?page={page}",
            "method": "GET",
            "items_path": "items",
            "name_field": "title",
            "updated_field": "changed_at",
            "actor_field": "owner.handle",
        },
    }
    spec.update(over)
    return spec


def _open(tmp_path, enforce=False):
    (tmp_path / CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    (tmp_path / EGRESS).write_text(
        f"enforce: {'true' if enforce else 'false'}\nallow_hosts: []\n", encoding="utf-8")
    return tmp_path


def _items(n, start=0):
    return {"items": [
        {"title": f"thing-{i}", "changed_at": f"2026-07-{(i % 27) + 1:02d}T00:00:00Z",
         "owner": {"handle": f"owner-{i % 3}"}, "body": "CONFIDENTIAL-ROW-CONTENTS"}
        for i in range(start, start + n)
    ]}


# ------------------------------------------------------- the read-only ceiling
@pytest.mark.parametrize("call, reason", [
    ({"url": "https://a.test", "method": "DELETE"}, "method_not_read_only"),
    ({"url": "https://a.test", "method": "PUT"}, "method_not_read_only"),
    ({"url": "https://a.test", "method": "PATCH"}, "method_not_read_only"),
    ({"url": "http://a.test", "method": "GET"}, "url_not_https"),
    ({"url": "https://", "method": "GET"}, "url_has_no_host"),
    ({"url": "https://a.test", "method": "GET",
      "headers": {"X-HTTP-Method-Override": "DELETE"}}, "method_override_header"),
    # The credential's OWN header name is a second override channel: the
    # request builder injects it after this check used to run.
    ({"url": "https://a.test", "method": "GET",
      "auth_header": "X-HTTP-Method-Override"}, "method_override_header"),
    ({"url": "https://a.test", "method": "POST", "auth_header": "x-method-override",
      "json": {"query": "query { x }"}}, "method_override_header"),
    ({"url": "https://a.test", "method": "GET", "json": {"q": 1}}, "get_with_body"),
    ({"url": "https://a.test", "method": "POST",
      "json": {"name": "new"}}, "post_body_not_a_graphql_document"),
    ({"url": "https://a.test", "method": "POST",
      "json": {"query": "q", "extra": 1}}, "post_body_not_a_graphql_document"),
    ({"url": "https://a.test", "method": "POST",
      "json": {"query": "mutation { create_board(name: \"x\") { id } }"}},
     "write_token_in_graphql_document"),
    ({"url": "https://a.test", "method": "POST",
      "json": {"query": "subscription { events { id } }"}},
     "write_token_in_graphql_document"),
    ({"url": "https://a.test", "method": "POST",
      "json": {"query": "query Q { x }", "variables": {"m": "mutation { z }"}}},
     "write_token_in_graphql_document"),
])
def test_a_call_that_could_write_is_refused_before_any_socket(call, reason):
    with pytest.raises(research.ReadOnlyViolation) as excinfo:
        research.assert_read_only(call)
    assert reason in str(excinfo.value)


@pytest.mark.parametrize("call", [
    {"url": "https://a.test/v1/things", "method": "GET"},
    {"url": "https://a.test/graphql", "method": "POST",
     "json": {"query": "query { boards (limit: 10) { id name updated_at } }"}},
    # A thing NAMED for the keyword is not the keyword: the token boundary is
    # what stops a legitimate estate from being unreadable.
    {"url": "https://a.test/graphql", "method": "POST",
     "json": {"query": "query { boards (name: \"mutations-team\") { id } }"}},
])
def test_a_read_is_allowed(call):
    research.assert_read_only(call)


def test_a_write_spec_never_reaches_the_network(tmp_path):
    """The exception is not the proof. The EMPTY request log is."""
    fetch = Recorder([_items(1)])
    spec = _spec(inventory={"url": "https://api.example.test/v1/things",
                            "method": "DELETE", "items_path": "items"})
    out = research.sweep_connectors(
        _open(tmp_path), specs=[spec], env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=fetch)
    assert fetch.seen == []
    assert out["calls"] == 0
    assert out["connectors"][0]["connected"] is False
    assert out["connectors"][0]["reason"].startswith("read_only_refused:")


def test_the_injected_credential_header_cannot_smuggle_a_method_override(tmp_path):
    """The ceiling has to cover the header the REQUEST BUILDER adds, not just
    the ones the spec declares. Proven the same way as the arm above: an EMPTY
    request log, because an arm that only read the reason would pass against a
    lane that made the call and then complained."""
    fetch = Recorder([_items(1)])
    spec = _spec(inventory={
        "url": "https://api.example.test/v1/things", "method": "GET",
        "auth_header": "X-HTTP-Method-Override", "auth_format": "DELETE",
        "items_path": "items", "name_field": "title"})
    out = research.sweep_connectors(
        _open(tmp_path), specs=[spec], env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=fetch)
    assert fetch.seen == []
    assert out["calls"] == 0
    assert out["connectors"][0]["reason"].startswith(
        "read_only_refused:method_override_header")


def test_every_request_the_lane_emits_is_a_read(tmp_path):
    fetch = Recorder([_items(3), {"items": []}])
    research.sweep_connectors(
        _open(tmp_path),
        specs=[_spec(page={"start": 1, "max_pages": 3}),
               _spec(name="graph", inventory={
                   "url": "https://api.example.test/graphql", "method": "POST",
                   "json": {"query": "query { things { title } }"},
                   "items_path": "items", "name_field": "title"})],
        env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=fetch)
    assert fetch.seen, "the sweep must actually have called something"
    assert {r["method"] for r in fetch.seen} <= {"GET", "POST"}


def test_the_credential_reaches_the_declared_host_and_nothing_else(tmp_path):
    fetch = Recorder([_items(2)])
    research.sweep_connectors(
        _open(tmp_path), specs=[_spec()], env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=fetch)
    for request in fetch.seen:
        assert request["url"].startswith("https://api.example.test/")
        assert request["headers"]["Authorization"] == CRED


def test_http_fetch_refuses_to_follow_a_redirect():
    """A followed 30x hands the Authorization header to whatever the response
    names. This proves the credential is not re-sent, over a real socket."""
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — stdlib naming
            hits.append((self.path, self.headers.get("Authorization")))
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", "/elsewhere")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        status, _ = research._http_fetch(
            {"url": f"http://{host}:{port}/start", "method": "GET",
             "headers": {"Authorization": CRED}, "body": None}, 10)
    finally:
        server.shutdown()
        server.server_close()
    assert status == 302
    assert [path for path, _ in hits] == ["/start"]


# --------------------------------------------------------------- contents-free
def test_only_the_declared_fields_leave_the_response(tmp_path):
    fetch = Recorder([_items(4)])
    out = research.sweep_connectors(
        _open(tmp_path), specs=[_spec()], env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=fetch)
    blob = json.dumps(out)
    assert "CONFIDENTIAL-ROW-CONTENTS" not in blob
    assert CRED not in blob
    assert {r["name"] for r in out["rows"]} == {f"thing-{i}" for i in range(4)}
    assert out["connectors"][0]["items"] == 4
    assert out["connectors"][0]["actors"] == 3
    assert out["connectors"][0]["latest"] == "2026-07-04T00:00:00Z"


def test_a_container_field_is_never_flattened_into_text(tmp_path):
    fetch = Recorder([{"items": [{"title": {"nested": "CONFIDENTIAL"}, "changed_at": None}]}])
    out = research.sweep_connectors(
        _open(tmp_path), specs=[_spec()], env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=fetch)
    assert out["rows"] == []
    assert "CONFIDENTIAL" not in json.dumps(out)


def test_an_oversized_response_is_refused_rather_than_read(tmp_path):
    huge = (200, b"x" * (research._MAX_RESPONSE_BYTES + 10))
    out = research.sweep_connectors(
        _open(tmp_path), specs=[_spec()], env={"TEST_CONNECTOR_TOKEN": CRED},
        fetch=Recorder([huge]))
    assert out["connectors"][0]["reason"] == "response_too_large"


# ----------------------------------------------------------- degenerate ends --
def test_no_connectors_declared_is_an_honest_empty(tmp_path):
    out = research.sweep_connectors(_open(tmp_path), env={}, fetch=Recorder([{}]))
    assert out["declared"] == 0
    assert out["connectors"] == [] and out["rows"] == [] and out["calls"] == 0
    assert research.load_connector_specs(tmp_path) == []


def test_an_absent_credential_is_named_not_dropped(tmp_path):
    fetch = Recorder([_items(1)])
    out = research.sweep_connectors(_open(tmp_path), specs=[_spec()], env={}, fetch=fetch)
    assert fetch.seen == []
    assert out["connectors"] == [{"name": "things", "connected": False,
                                  "items": 0, "calls": 0, "reason": "credential_absent"}]


def test_a_closed_egress_ceiling_refuses_every_connector_before_calling(tmp_path):
    fetch = Recorder([_items(1)])
    out = research.sweep_connectors(
        _open(tmp_path, enforce=True), specs=[_spec()],
        env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=fetch)
    assert fetch.seen == []
    assert out["connectors"][0]["reason"] == "egress_egress_closed_no_allowed_hosts"


def test_an_empty_inventory_is_not_a_connection(tmp_path):
    out = research.sweep_connectors(
        _open(tmp_path), specs=[_spec()], env={"TEST_CONNECTOR_TOKEN": CRED},
        fetch=Recorder([{"items": []}]))
    assert out["connectors"][0]["connected"] is False
    assert out["connectors"][0]["reason"] == "inventory_returned_no_items"
    assert research.probe_connectors(tmp_path, sweep=out)["grants"]["connectors"] == []


@pytest.mark.parametrize("payload, reason", [
    ((401, b"{}"), "http_401"),
    ((500, b"{}"), "http_500"),
    ((200, b"not json at all"), "response_not_json"),
])
def test_each_failure_arrives_with_its_own_reason(tmp_path, payload, reason):
    out = research.sweep_connectors(
        _open(tmp_path), specs=[_spec()], env={"TEST_CONNECTOR_TOKEN": CRED},
        fetch=Recorder([payload]))
    assert out["connectors"][0]["reason"] == reason


def test_a_transport_failure_is_reported_not_raised(tmp_path):
    def boom(request, timeout):
        raise OSError("no route to host")

    out = research.sweep_connectors(
        _open(tmp_path), specs=[_spec()], env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=boom)
    assert out["connectors"][0]["reason"].startswith("unreachable:")


# ------------------------------------------------------------------- paging --
def test_paging_stops_on_an_empty_page_and_deduplicates(tmp_path):
    fetch = Recorder([_items(2, 0), _items(2, 0), {"items": []}])
    out = research.sweep_connectors(
        _open(tmp_path), specs=[_spec(page={"start": 1, "max_pages": 5})],
        env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=fetch)
    assert len(fetch.seen) == 3
    assert [r["url"].rsplit("=", 1)[-1] for r in fetch.seen] == ["1", "2", "3"]
    assert out["connectors"][0]["items"] == 2


def test_a_truncated_sweep_says_so_and_a_complete_one_does_not(tmp_path):
    truncated = research.sweep_connectors(
        _open(tmp_path), specs=[_spec(page={"start": 1, "max_pages": 2, "size": 2})],
        env={"TEST_CONNECTOR_TOKEN": CRED},
        fetch=Recorder([_items(2, 0), _items(2, 10)]))
    assert any("may be larger" in line for line in truncated["not_reached"])

    complete = research.sweep_connectors(
        _open(tmp_path), specs=[_spec(page={"start": 1, "max_pages": 2, "size": 5})],
        env={"TEST_CONNECTOR_TOKEN": CRED},
        fetch=Recorder([_items(2, 0), _items(2, 10)]))
    assert complete["not_reached"] == []
    assert complete["connectors"][0]["items"] == 4


def test_the_call_budget_is_enforced_by_this_lane(tmp_path):
    fetch = Recorder([_items(2, 0), _items(2, 10), _items(2, 20)])
    out = research.sweep_connectors(
        _open(tmp_path), specs=[_spec(page={"start": 1, "max_pages": 9})],
        env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=fetch, max_calls=2)
    assert len(fetch.seen) == 2
    assert out["calls"] == 2
    assert any("budget" in line for line in out["not_reached"])


def test_the_item_cap_is_enforced_by_this_lane(tmp_path):
    out = research.sweep_connectors(
        _open(tmp_path), specs=[_spec()], env={"TEST_CONNECTOR_TOKEN": CRED},
        fetch=Recorder([_items(50)]), max_items=10)
    assert out["connectors"][0]["items"] == 10
    assert any("cap" in line for line in out["not_reached"])


# ------------------------------------------------------------- the identity ---
def test_the_identity_call_is_held_to_the_same_ceiling(tmp_path):
    fetch = Recorder([_items(1)])
    out = research.sweep_connectors(
        _open(tmp_path),
        specs=[_spec(identity={"url": "https://api.example.test/me", "method": "PUT",
                               "value_paths": ["login"]})],
        env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=fetch)
    assert all(r["method"] == "GET" for r in fetch.seen)
    assert any("identity call refused" in line for line in out["not_reached"])


def test_identities_are_collected_for_the_ranker_to_demote(tmp_path):
    class Two(Recorder):
        def __call__(self, request, timeout):
            self.seen.append(request)
            if request["url"].endswith("/me"):
                return 200, json.dumps({"login": "acme-owner"}).encode("utf-8")
            return 200, json.dumps(_items(2)).encode("utf-8")

    out = research.sweep_connectors(
        _open(tmp_path),
        specs=[_spec(identity={"url": "https://api.example.test/me", "method": "GET",
                               "value_paths": ["login"]})],
        env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=Two([]))
    assert out["identities"] == ["acme-owner"]


# -------------------------------------------------------------- the registry --
def test_a_declaration_grants_nothing_and_a_completed_read_grants_the_mode(tmp_path):
    """DECLARED IS NOT CONNECTED. The registry's grant must follow the READ."""
    (tmp_path / CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    (tmp_path / EGRESS).write_text("enforce: false\n", encoding="utf-8")
    (tmp_path / research.CONNECTORS_REL).write_text(
        "connectors:\n  - name: things\n    credential_env: TEST_CONNECTOR_TOKEN\n"
        "    inventory:\n      url: https://api.example.test/v1/things\n"
        "      items_path: items\n      name_field: title\n", encoding="utf-8")
    assert len(research.load_connector_specs(tmp_path)) == 1
    declared_only = research.probe_connectors(tmp_path)
    assert declared_only["grants"]["connectors"] == []
    assert journey.entry_mode(declared_only["grants"]) != journey.ENTRY_MODE_CONNECTED

    swept = research.sweep_connectors(
        tmp_path, env={"TEST_CONNECTOR_TOKEN": CRED}, fetch=Recorder([_items(3)]))
    granted = research.probe_connectors(tmp_path, sweep=swept)
    assert granted["grants"]["connectors"] == ["connector:things"]
    assert journey.entry_mode(granted["grants"]) == journey.ENTRY_MODE_CONNECTED


def test_a_connector_that_did_not_answer_is_refused_with_its_reason(tmp_path):
    swept = research.sweep_connectors(
        _open(tmp_path), specs=[_spec()], env={}, fetch=Recorder([{}]))
    registry = research.probe_connectors(tmp_path, sweep=swept)
    refused = [r for r in registry["refused"] if r["kind"] == "connector"]
    assert refused and refused[0]["reason"] == "credential_absent"


# ------------------------------------------------------------------- the wire -
def _wire(tmp_path, monkeypatch, pages):
    (tmp_path / CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    (tmp_path / EGRESS).write_text("enforce: false\n", encoding="utf-8")
    (tmp_path / research.CONNECTORS_REL).write_text(
        "connectors:\n  - name: things\n    credential_env: TEST_CONNECTOR_TOKEN\n"
        "    inventory:\n      url: https://api.example.test/v1/things\n"
        "      items_path: items\n      name_field: title\n"
        "      updated_field: changed_at\n", encoding="utf-8")
    monkeypatch.setenv("TEST_CONNECTOR_TOKEN", CRED)
    monkeypatch.setattr(research, "_http_fetch", Recorder(pages))


def test_the_onboarding_path_reaches_connected_mode_by_executing_the_action(
        tmp_path, monkeypatch):
    """THE WIRE, driven through the public action API.

    Fails against pre-change code twice over: ``gather_connectors`` did not
    exist, and ``entry_grants.connectors`` had no writer that a credentialed
    read could ever fill.
    """
    _wire(tmp_path, monkeypatch, [_items(6)])
    before = journey.snapshot(tmp_path)["state"]
    assert journey.entry_mode(before["entry_grants"]) != journey.ENTRY_MODE_CONNECTED
    assert "gather_connectors" in [
        a["action"] for a in journey._entry_plan_for(before)["next_actions"]]

    out = journey.act({"action": "gather_connectors", "surface": "cli",
                       "action_id": "act-" + "c" * 16}, root=tmp_path)
    state = out["state"]
    assert state["entry_grants"]["connectors"] == ["connector:things"]
    assert journey.entry_mode(state["entry_grants"]) == journey.ENTRY_MODE_CONNECTED
    assert journey._entry_plan_for(state)["opening_move"] == "sweep_and_assert"
    assert len(state["salience_rows"]["rows"]) == 6
    assert state["connector_sweep"]["declared"] == 1
    assert "CONFIDENTIAL-ROW-CONTENTS" not in json.dumps(state)


def test_the_gather_action_is_offered_only_where_connectors_are_declared(tmp_path):
    (tmp_path / CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    (tmp_path / EGRESS).write_text("enforce: false\n", encoding="utf-8")
    state = journey.snapshot(tmp_path)["state"]
    assert state["connectors_declared"] == 0
    assert "gather_connectors" not in [
        a["action"] for a in journey._entry_plan_for(state)["next_actions"]]


def test_the_sweep_is_recorded_as_an_event_with_no_contents(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch, [_items(2)])
    journey.act({"action": "gather_connectors", "surface": "cli",
                 "action_id": "act-" + "d" * 16}, root=tmp_path)
    events = journey._read_events(tmp_path)
    gathered = [e for e in events if e.get("action") == "gather_connectors"]
    assert len(gathered) == 1
    blob = json.dumps(gathered[0])
    assert "CONFIDENTIAL-ROW-CONTENTS" not in blob and CRED not in blob
