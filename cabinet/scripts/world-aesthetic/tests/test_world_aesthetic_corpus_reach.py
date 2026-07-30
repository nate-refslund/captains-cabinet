"""The corpus's own arm: can CI SEE the members it claims to judge?

WHY THIS FILE EXISTS. Five arms of this suite read the calibration corpus, the
corpus is gitignored, and every one of them used to `pytest.skip` when it was
absent — which is always, on a fresh checkout. So the one environment that runs
those arms was the one where they could not run, and CI had never seen them
either pass or fail. That is the disabled-sensor class this repo keeps finding
in its own tests, sitting inside the gate that polices the world's look.

It was worse than a skip, because the gate was not even consistent. Measured
2026-07-30 against ONE commit:

    the manifest's own corpus on disk  ->  96 passed
    the ARCHIVED pre-re-fit corpus     ->   4 failed (unattributable)
    a fresh CI checkout                ->   5 skipped

Three verdicts, one tree. `has_corpus` asked whether any PNG existed in
corpus/positive/ and never whether it was the corpus the tracked manifest
declares, so a wrong corpus could redden the suite — or, far worse, pass it.

The fix has three parts and this file is the arm on all three:
  * every member the repo can REBUILD is materialised before the arms run, so
    they execute in CI instead of skipping;
  * every member present is sha256-verified against the tracked manifest, and a
    mismatch fails loudly by id rather than skipping or quietly passing;
  * the members that genuinely cannot be reconstructed are DECLARED, and the
    declaration is pinned here — so a member cannot join the held set silently,
    which would be the "partial fix that relabels the rest as covered" move.
"""

from __future__ import annotations

import hashlib
import json

import pytest

# Held = the pixels exist only where they were captured or received. Pinned by
# ID rather than by count: a count cannot tell "a positive became rebuildable"
# from "a rebuildable negative was quietly dropped into the held pile".
HELD = {
    # Live renderer captures. Reproducing them byte-identically would mean
    # pinning the whole renderer, which is the thing they exist to judge.
    "pos-owned-island-hamlet",
    "pos-owned-island-camp",
    "pos-owned-square-close",
    "pos-owned-interior-cutaway",
    # Captain-rejected build screenshots from the LimeZu era. Ground-truth
    # judgment data, and licensed art that this repo may not redistribute —
    # which matters more now the tree is headed for a public export.
    "neg-island-void",
    "neg-city-street-void",
    "neg-grey-wardroom",
}

REBUILDABLE = {
    "neg-owned-scatter-sparse": "synthetic",
    "neg-owned-scatter-dense": "synthetic",
    "neg-owned-void": "synthetic",
    "pal-owned-atlas": "copy:cabinet/dashboard/public/world-assets/originals/"
                       "iso/atlas-0.png",
}


def _probe_conftest(wa):
    """A fresh exec of conftest.py, so its verifier can be called directly."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "wa_conftest_probe", wa.dir / "tests" / "conftest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _manifest(wa) -> dict:
    return json.loads((wa.corpus_dir / "manifest.json").read_text())


def test_every_member_declares_whether_a_checkout_can_rebuild_it(wa):
    """No member may be undeclared — an undeclared one is a silent skip."""
    reg = wa.builder.REGISTRY
    assert set(reg) == HELD | set(REBUILDABLE), (
        "the corpus registry and this arm disagree about which members exist; "
        "adding a member means declaring here whether CI can see it")
    for entry_id, row in reg.items():
        rebuild = row[4]
        if entry_id in HELD:
            assert rebuild is None, (
                f"{entry_id} is pinned HELD here but the registry now claims a "
                f"rebuild recipe {rebuild!r} — one of the two is wrong, and the "
                f"dangerous direction is a held member reported as covered")
        else:
            assert rebuild == REBUILDABLE[entry_id], (
                f"{entry_id}'s rebuild recipe changed to {rebuild!r}; a recipe "
                f"drift is how an arm stops running in CI without anyone seeing "
                f"a single line change in the test")


def test_the_rebuildable_members_are_actually_on_disk_and_pixel_exact(wa):
    """THE ARM THAT MATTERS: the recipes RAN, and produced the declared PICTURE.

    A recipe that has quietly stopped working leaves the same result as no
    recipe at all — the arms downstream skip — so nothing short of hashing the
    output proves CI can see these members.

    PIXELS, not bytes, and that distinction was paid for. All four regenerate
    byte-identically on the machine that built them, three times over; the first
    ubuntu runner that tried produced the same PICTURES as different FILES,
    because PNG encoding runs through whatever zlib the local Pillow was built
    against. A reproducibility claim measured at one operating point is a
    hypothesis. The file digest still governs the HELD members — for those the
    bytes are all anyone has.
    """
    by_id = {i["id"]: i for i in _manifest(wa)["images"]}
    for entry_id in sorted(REBUILDABLE):
        img = by_id[entry_id]
        p = wa.dir / img["file"]
        assert p.is_file(), (
            f"{entry_id} is declared rebuildable and is NOT on disk after the "
            f"fixture materialised the corpus — its recipe has stopped working, "
            f"and every arm that reads it is skipping in CI right now")
        assert img.get("pixels_sha256"), (
            f"{entry_id} carries no pixels_sha256; a rebuildable member verified "
            f"by file bytes alone is a corpus that only one machine can hold")
        assert wa.builder.pixels_sha256_of(p) == img["pixels_sha256"], (
            f"{entry_id} rebuilt to a different PICTURE than the manifest "
            f"records — the recipe is no longer deterministic, so the corpus "
            f"the arms judge is not the corpus this tree declares")


def test_the_held_members_are_reported_by_name_never_relabelled_as_covered(wa):
    """A held member must show up in `wa.held`, so an arm running on a partial
    corpus has to say so instead of reporting a whole-corpus pass."""
    on_disk = {i["id"] for i in _manifest(wa)["images"]
               if (wa.dir / i["file"]).is_file()}
    for entry_id in sorted(HELD - on_disk):
        assert entry_id in wa.held, (
            f"{entry_id} is absent AND is not named in wa.held — an arm reading "
            f"the corpus would report a clean pass over a set it never saw")


def test_a_missing_pillow_fails_when_it_costs_coverage_and_not_otherwise(wa):
    """Pillow builds the synthetic negatives, and its absence must not quietly
    restore the skip this whole fixture removed.

    Two directions, because only failing one of them proves anything. Rebuildable
    members ABSENT and no Pillow = arms would skip = a hard failure naming them.
    Rebuildable members already ON DISK and no Pillow = nothing is lost, and the
    stdlib-only gates must still run — the suite advertises itself as needing no
    Pillow, so failing there would be an invented blocker.
    """
    import types

    mod = _probe_conftest(wa)

    def builder_without_pillow(registry):
        b = types.SimpleNamespace(REGISTRY=registry,
                                  pixels_sha256_of=wa.builder.pixels_sha256_of)

        def boom(_corpus):
            raise ImportError("No module named 'PIL'")
        b.materialise = boom
        return b

    absent = {"neg-fake-absent": ("negative", "neg-fake-absent.png", "p", "w",
                                  "synthetic")}
    # pytest.fail.Exception, NOT Exception: `Failed` derives from BaseException,
    # so `pytest.raises(Exception)` walks straight past it — which is how a test
    # written to catch a hard failure can report the failure as its own red and
    # tell you nothing about the guard.
    with pytest.raises(pytest.fail.Exception) as caught:
        mod._corpus_state(builder_without_pillow(absent))
    assert "neg-fake-absent" in str(caught.value), (
        "a rebuildable member that could NOT be built was not named — the arms "
        "reading it are skipping and nothing says so")

    # Every rebuildable member IS on disk (the session fixture materialised
    # them), so this direction must NOT fail.
    _v, held, mismatch = mod._corpus_state(builder_without_pillow(wa.builder.REGISTRY))
    assert not mismatch
    assert set(REBUILDABLE) <= set(wa.builder.REGISTRY)
    assert held, "with no Pillow every member is reported held until verified"


def test_a_corpus_that_does_not_match_the_manifest_is_a_failure_not_a_skip(wa):
    """The 2026-07-30 case, reproduced: a member present but not the declared one.

    That is not hypothetical — the archive ships in this tree at
    corpus/archive-limezu-2026-07-08/, one `cp -R` from being mistaken for the
    live corpus, and doing exactly that turned 96 green into 4 unattributable
    red. The verifier has to name the mismatching id; the old `has_corpus` glob
    could not distinguish it from the real thing in either direction.

    The victim is a REBUILDABLE member with its PIXELS changed, so this arm runs
    on a fresh checkout where the held members do not exist.
    """
    mod = _probe_conftest(wa)
    victim = next(i for i in _manifest(wa)["images"] if i["id"] in REBUILDABLE)
    p = wa.dir / victim["file"]
    original = p.read_bytes()
    try:
        w, h, buf = wa.gates._png.decode(p)
        buf = bytearray(buf)
        buf[0] ^= 0xFF                                  # one pixel, one channel
        wa.gates._png.encode(p, w, h, bytes(buf))
        _verified, _held, mismatch = mod._corpus_state(wa.builder)
        assert victim["id"] in mismatch, (
            "a member whose PICTURE does not match the manifest was NOT reported "
            "as a mismatch — which is how one commit produced three different "
            "verdicts on three machines")
    finally:
        p.write_bytes(original)


def test_a_mere_RE_ENCODE_of_a_rebuilt_member_is_not_a_mismatch(wa):
    """THE ARM FOR THE DEFECT THAT BROKE CI, and the reason two digests exist.

    A rebuilt PNG is re-encoded by the local zlib, so the same picture lands as
    different FILE bytes on a different machine. Measured: the synthetic
    negatives regenerated byte-identically three times on one laptop and
    byte-differently on the first ubuntu runner that tried, which reddened 74
    tests with a corpus that was in fact correct.

    Without this arm the fix is a claim. With it, a future change that goes back
    to comparing file bytes for a GENERATED member fails here rather than in CI.
    """
    mod = _probe_conftest(wa)
    victim = next(i for i in _manifest(wa)["images"] if i["id"] in REBUILDABLE)
    p = wa.dir / victim["file"]
    original = p.read_bytes()
    try:
        w, h, buf = wa.gates._png.decode(p)
        # Same PIXELS, different FILE: _png.encode always writes ct6/filter-0
        # with its own zlib settings, so a ct2 source comes back byte-different
        # and decodes to the identical RGBA buffer — which is exactly the shape
        # of the cross-machine re-encode this arm exists for.
        wa.gates._png.encode(p, w, h, buf)
        assert p.read_bytes() != original, (
            "the re-encode produced identical bytes, so this arm proved nothing "
            "— it has to actually change the file to test that the change is "
            "tolerated")
        _verified, _held, mismatch = mod._corpus_state(wa.builder)
        assert victim["id"] not in mismatch, (
            f"{victim['id']} was called a mismatch for being re-encoded — that "
            "is the CI failure of 2026-07-30, where a correct corpus reddened "
            "74 tests because a GENERATED member was judged by its file bytes")
    finally:
        p.write_bytes(original)
