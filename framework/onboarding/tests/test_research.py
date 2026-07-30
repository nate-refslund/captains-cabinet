"""research_repo — read a LOCAL product repo into a profile. No network, no secrets."""
import inspect
import json

from framework.onboarding import research


def _mk_repo(tmp_path, *, pkg=None, readme=None, claude=None, mcp=None, env=None, remote=None):
    if pkg is not None:
        (tmp_path / "package.json").write_text(json.dumps(pkg))
    if readme is not None:
        (tmp_path / "README.md").write_text(readme)
    if claude is not None:
        d = tmp_path / ".claude"; d.mkdir(exist_ok=True)
        (d / "settings.json").write_text(json.dumps(claude))
    if mcp is not None:
        (tmp_path / ".mcp.json").write_text(json.dumps(mcp))
    if env is not None:
        (tmp_path / ".env").write_text(env)
    if remote is not None:
        g = tmp_path / ".git"; g.mkdir(exist_ok=True)
        (g / "config").write_text(f'[remote "origin"]\n\turl = {remote}\n')
    return tmp_path


def test_reads_name_and_summary(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "acme-shop"},
             readme="# Acme Shop\n\nDemo storefront platform.\n\nmore.")
    p = research.research_repo(str(tmp_path))
    assert p["name"] == "acme-shop"
    assert "demo storefront" in p["summary"].lower()


def test_detects_stack_from_deps(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "x",
                            "dependencies": {"next": "15", "@neondatabase/serverless": "1"}})
    p = research.research_repo(str(tmp_path))
    assert "nextjs" in p["stack"] and "neon" in p["stack"]


def test_detects_plugins_from_claude_and_mcp(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "x"},
             claude={"enabledPlugins": ["dev-tasks@dev-tasks-marketplace"]},
             mcp={"mcpServers": {"corridor": {}, "neon": {}}})
    p = research.research_repo(str(tmp_path))
    assert "dev-tasks" in p["plugins"]
    assert "corridor" in p["plugins"]


def test_normalizes_git_remote(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "x"}, remote="https://github.com/acme-org/x.git")
    assert research.research_repo(str(tmp_path))["repo_url"] == "https://github.com/acme-org/x"


def test_normalizes_ssh_remote(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "x"}, remote="git@github.com:acme-org/x.git")
    assert research.research_repo(str(tmp_path))["repo_url"] == "https://github.com/acme-org/x"


def test_never_surfaces_env_secrets(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "x"}, env="SECRET_TOKEN=supersecretvalue\n")
    blob = json.dumps(research.research_repo(str(tmp_path)))
    assert "supersecretvalue" not in blob  # .env is never read


def test_has_claude_flag(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "x"})
    assert research.research_repo(str(tmp_path))["has_claude"] is False
    _mk_repo(tmp_path, pkg={"name": "x"}, claude={})
    assert research.research_repo(str(tmp_path))["has_claude"] is True


# ---------------------------------------------------------------------------
# inventory_mcp_estate — consent-gated, NAMES only (Phase 2 purpose-first)
# ---------------------------------------------------------------------------
def _mk_estate(tmp_path, *, mcp=None, extensions=None, example=None):
    if mcp is not None:
        (tmp_path / ".mcp.json").write_text(json.dumps(mcp))
    cfg = tmp_path / "instance" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    if extensions is not None:
        (cfg / "extensions.yml").write_text(extensions)
    if example is not None:
        (cfg / "extensions.yml.example").write_text(example)
    return tmp_path


_NO_CONSENT = {"consented": False, "servers": [], "sources": []}


def test_inventory_without_consent_is_honest_refusal(tmp_path):
    _mk_estate(tmp_path, mcp={"mcpServers": {"neon": {}}},
               extensions="mcps:\n  - name: brain-bridge\n")
    assert research.inventory_mcp_estate(str(tmp_path)) == _NO_CONSENT


def test_inventory_consent_must_be_exactly_true(tmp_path):
    """Truthy-but-not-True never opens the gate — consent is an explicit
    Captain yes, not an accident of a truthy flag."""
    _mk_estate(tmp_path, mcp={"mcpServers": {"neon": {}}})
    for sloppy in ("yes", 1, [True]):
        assert research.inventory_mcp_estate(
            str(tmp_path), consent=sloppy) == _NO_CONSENT


def test_inventory_no_consent_never_touches_files(tmp_path, monkeypatch):
    """Null-hatch spirit as a tested property: the no-consent path performs
    ZERO filesystem work — even constructing a Path fails the test."""
    def boom(*a, **k):
        raise AssertionError("no reads without consent")
    monkeypatch.setattr(research, "_read_json", boom)
    monkeypatch.setattr(research, "Path", boom)   # the module's only fs door
    assert research.inventory_mcp_estate(str(tmp_path)) == _NO_CONSENT


def test_inventory_with_consent_lists_names_from_both_surfaces(tmp_path):
    _mk_estate(
        tmp_path,
        mcp={"mcpServers": {"neon": {"type": "http"}, "library": {}}},
        extensions="mcps:\n  - name: brain-bridge\n    url: http://127.0.0.1:1\n")
    out = research.inventory_mcp_estate(str(tmp_path), consent=True)
    assert out["consented"] is True
    assert out["servers"] == ["brain-bridge", "library", "neon"]   # sorted, deduped
    assert out["sources"] == [".mcp.json", "instance/config/extensions.yml"]


def test_inventory_surfaces_names_only_never_values(tmp_path):
    _mk_estate(tmp_path, mcp={"mcpServers": {"neon": {
        "type": "http", "url": "https://mcp.internal.example/mcp",
        "headers": {"Authorization": "Bearer supersecretvalue"},
        "env": {"NEON_API_KEY": "leaked-value"},
    }}})
    blob = json.dumps(research.inventory_mcp_estate(str(tmp_path), consent=True))
    assert "neon" in blob                      # the NAME
    for value in ("supersecretvalue", "leaked-value", "mcp.internal.example",
                  "Authorization", "NEON_API_KEY"):
        assert value not in blob               # never anything but names


def test_inventory_falls_back_to_example_and_prefers_real(tmp_path):
    _mk_estate(tmp_path, example="mcps:\n  - name: example-server\n")
    out = research.inventory_mcp_estate(str(tmp_path), consent=True)
    assert out["servers"] == ["example-server"]
    assert out["sources"] == ["instance/config/extensions.yml.example"]
    _mk_estate(tmp_path, extensions="mcps:\n  - name: real-server\n")
    out2 = research.inventory_mcp_estate(str(tmp_path), consent=True)
    assert out2["servers"] == ["real-server"]  # the real file wins
    assert out2["sources"] == ["instance/config/extensions.yml"]


def test_inventory_bare_root_and_malformed_are_honest_empties(tmp_path):
    out = research.inventory_mcp_estate(str(tmp_path), consent=True)
    assert out == {"consented": True, "servers": [], "sources": []}
    _mk_estate(tmp_path, extensions="mcps: [unclosed")   # guaranteed parse error
    (tmp_path / ".mcp.json").write_text("{ not json")
    out2 = research.inventory_mcp_estate(str(tmp_path), consent=True)
    assert out2["servers"] == [] and out2["sources"] == []   # empty, never a raise


def test_inventory_tolerates_empty_and_null_mcps_blocks(tmp_path):
    _mk_estate(tmp_path, extensions="mcps: []\n")
    assert research.inventory_mcp_estate(str(tmp_path), consent=True)["servers"] == []
    _mk_estate(tmp_path, extensions="plugins: []\n")     # no mcps key at all
    assert research.inventory_mcp_estate(str(tmp_path), consent=True)["servers"] == []


# --- claim surface: `sources` says what it is, not what a reader would hope ---


def test_sources_names_what_yielded_a_reading_not_what_was_consulted(tmp_path):
    """The docstring promised "the root-relative paths actually consulted".

    A file that exists and will not parse IS consulted — read off disk, handed
    to a parser, thrown away — and then omitted, so a broken pair returns the
    same document as a bare root: "I looked and it was unreadable" and "there
    was nothing to look at" arriving as one answer. The behaviour is deliberate
    and pinned by test_inventory_bare_root_and_malformed_are_honest_empties;
    what was wrong was the sentence, so this arm holds the sentence to it.
    """
    (tmp_path / ".mcp.json").write_text('{"mcpServers": ', encoding="utf-8")
    (tmp_path / "instance" / "config").mkdir(parents=True)
    (tmp_path / "instance" / "config" / "extensions.yml").write_text(
        "mcps: [unclosed", encoding="utf-8")

    out = research.inventory_mcp_estate(str(tmp_path), consent=True)
    # Both were there to consult, and neither is named in the result.
    assert (tmp_path / ".mcp.json").is_file()
    assert (tmp_path / "instance" / "config" / "extensions.yml").is_file()
    assert out["sources"] == []
    assert out == research.inventory_mcp_estate(str(tmp_path / "nothing-here"),
                                                consent=True)

    doc = " ".join(inspect.getdoc(research.inventory_mcp_estate).split())
    assert "the root-relative paths actually consulted" not in doc
    assert "the paths a declaration block was read FROM" in doc


def test_sources_omits_a_read_path_that_declared_nothing(tmp_path):
    """The replacement sentence was over-broad too, one grain finer.

    It said ``sources`` names the paths that yielded a reading. A ``.mcp.json``
    that is VALID JSON and parsed without error, carrying no ``mcpServers``,
    yielded a reading and is still absent — while an extensions file parsed with
    no ``mcps:`` at all is listed. One sentence cannot be true of both limbs, so
    the asymmetry is measured HERE and stated in the docstring rather than
    described away. The behaviour is untouched: what ships wrong is the sentence.

    The asymmetry is derived by EXECUTION over two roots that differ only in
    which surface declares nothing — never by reading the branch structure the
    docstring is being held to, which is the assumption under audit.
    """
    empty_mcp = tmp_path / "declares-nothing"
    (empty_mcp / "instance" / "config").mkdir(parents=True)
    (empty_mcp / ".mcp.json").write_text("{}", encoding="utf-8")
    (empty_mcp / "instance" / "config" / "extensions.yml").write_text(
        "plugins: []\n", encoding="utf-8")
    out = research.inventory_mcp_estate(str(empty_mcp), consent=True)

    # Both files exist, both parse, neither declares a server.
    assert (empty_mcp / ".mcp.json").is_file()
    assert json.loads((empty_mcp / ".mcp.json").read_text(encoding="utf-8")) == {}
    assert out["servers"] == []
    # ...and the two surfaces are reported differently for the same situation.
    assert ".mcp.json" not in out["sources"]
    assert out["sources"] == ["instance/config/extensions.yml"]

    doc = " ".join(inspect.getdoc(research.inventory_mcp_estate).split())
    assert "NOT every path read" in doc
    assert "``.mcp.json`` parsed fine without ``mcpServers`` is absent" in doc
    assert "``mcps:`` is listed" in doc
