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


def test_the_rebuildable_members_are_actually_on_disk_and_byte_exact(wa):
    """THE ARM THAT MATTERS: the recipes RAN, and produced the declared bytes.

    A recipe that has quietly stopped working leaves the same result as no
    recipe at all — the arms downstream skip — so nothing short of hashing the
    output proves CI can see these members. Measured: all four regenerate
    sha256-identical to the tracked manifest from the repo's own tracked pack.
    """
    by_id = {i["id"]: i for i in _manifest(wa)["images"]}
    for entry_id in sorted(REBUILDABLE):
        img = by_id[entry_id]
        p = wa.dir / img["file"]
        assert p.is_file(), (
            f"{entry_id} is declared rebuildable and is NOT on disk after the "
            f"fixture materialised the corpus — its recipe has stopped working, "
            f"and every arm that reads it is skipping in CI right now")
        assert hashlib.sha256(p.read_bytes()).hexdigest() == img["sha256"], (
            f"{entry_id} rebuilt to different bytes than the manifest records — "
            f"the recipe is no longer deterministic, so the corpus the arms "
            f"judge is not the corpus this tree declares")


def test_the_held_members_are_reported_by_name_never_relabelled_as_covered(wa):
    """A held member must show up in `wa.held`, so an arm running on a partial
    corpus has to say so instead of reporting a whole-corpus pass."""
    on_disk = {i["id"] for i in _manifest(wa)["images"]
               if (wa.dir / i["file"]).is_file()}
    for entry_id in sorted(HELD - on_disk):
        assert entry_id in wa.held, (
            f"{entry_id} is absent AND is not named in wa.held — an arm reading "
            f"the corpus would report a clean pass over a set it never saw")


def test_a_corpus_that_does_not_match_the_manifest_is_a_failure_not_a_skip(wa,
                                                                          tmp_path):
    """The 2026-07-30 case, reproduced: the ARCHIVED corpus dropped in place.

    That is not a hypothetical — the archive ships in this tree at
    corpus/archive-limezu-2026-07-08/, one `cp -R` from being mistaken for the
    live corpus, and doing exactly that turned 96 green into 4 unattributable
    red. The verifier has to name the mismatching id; the old `has_corpus` glob
    could not distinguish it from the real thing in either direction.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "wa_conftest_probe", wa.dir / "tests" / "conftest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    man = _manifest(wa)
    victim = next(i for i in man["images"] if i["id"] in REBUILDABLE)
    p = wa.dir / victim["file"]
    original = p.read_bytes()
    try:
        p.write_bytes(original + b"\x00")          # same path, different bytes
        _verified, _held, mismatch = mod._corpus_state(wa.builder)
        assert victim["id"] in mismatch, (
            "a member whose bytes do not match the manifest was NOT reported as "
            "a mismatch — which is how one commit produced three different "
            "verdicts on three machines")
    finally:
        p.write_bytes(original)
