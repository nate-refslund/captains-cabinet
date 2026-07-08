"""Vision-judge protocol tests — aggregation math + calibration gating.

Everything runs on synthetic tmp corpora (tiny solid-color PNGs via the
stdlib codec), so a clean clone with no licensed corpus still proves the
mechanism — same contract as the gates suite.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

WA_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


@pytest.fixture(scope="module")
def judge():
    loader = _load("world_aesthetic_loader", WA_DIR / "_loader.py")
    return loader.load_judge()


@pytest.fixture(scope="module")
def png(judge):
    return judge._corpus.png_codec()


def solid_png(png, path: Path, w: int, h: int, rgba: tuple) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    png.encode(path, w, h, bytes(rgba) * (w * h))
    return path


def make_corpus(png, judge, root: Path, n_pos: int = 5,
                n_neg: int = 2) -> Path:
    corpus = root / "corpus"
    images = []
    for i in range(n_pos):
        f = solid_png(png, corpus / "positive" / f"pos-{i}.png",
                      8, 8, (10 + i * 17, 200, 60, 255))
        images.append({"id": f"pos-{i}", "class": "positive",
                       "file": f"corpus/positive/pos-{i}.png",
                       "sha256": judge._corpus.sha256_of(f),
                       "provenance": "synthetic-test", "why": "test pos"})
    for i in range(n_neg):
        f = solid_png(png, corpus / "negative" / f"neg-{i}.png",
                      8, 8, (90, 30 + i * 31, 190, 255))
        images.append({"id": f"neg-{i}", "class": "negative",
                       "file": f"corpus/negative/neg-{i}.png",
                       "sha256": judge._corpus.sha256_of(f),
                       "provenance": "synthetic-test", "why": "test neg"})
    judge._corpus.atomic_write_json(corpus / "manifest.json", {
        "purpose": "test", "note": "test",
        "counts": {"positive": n_pos, "negative": n_neg},
        "images": images,
    })
    return corpus


@pytest.fixture()
def run_bundle(tmp_path, judge, png):
    """A built 5-pos/2-neg run with one candidate (10 cal + 7 cand tasks)."""
    corpus = make_corpus(png, judge, tmp_path)
    cand = solid_png(png, tmp_path / "cand.png", 8, 8, (240, 180, 40, 255))
    run_dir, run_doc = judge.judge_protocol.build_run(
        [cand], corpus_dir=corpus, out_root=tmp_path / "runs", seed=1234)
    return run_dir, run_doc, corpus, cand


def author_results(run_dir: Path, cal_wrong: int = 0,
                   pos_wins: int | None = None,
                   neg_wins: int | None = None,
                   drop: int = 0, mutate=None) -> Path:
    """Write a results.json: calibration answered correctly except the
    first `cal_wrong` pairs; candidate wins the first `pos_wins`/`neg_wins`
    pairs per class (None = wins all)."""
    key = json.loads((run_dir / "key.json").read_text())
    run = json.loads((run_dir / "run.json").read_text())
    flip = {"LEFT": "RIGHT", "RIGHT": "LEFT"}
    answers = []
    cal_left, pos_left, neg_left = cal_wrong, pos_wins, neg_wins
    for tid in sorted(key["tasks"]):
        k = key["tasks"][tid]
        if k["kind"] == "calibration":
            if cal_left > 0:
                cal_left -= 1
                choice, why = flip[k["positive_side"]], "miscall"
            else:
                choice, why = k["positive_side"], "finished scene"
        else:
            if k["opponent_class"] == "positive":
                win = True if pos_left is None else pos_left > 0
                pos_left = None if pos_left is None else max(0, pos_left - 1)
            else:
                win = True if neg_left is None else neg_left > 0
                neg_left = None if neg_left is None else max(0, neg_left - 1)
            choice = k["candidate_side"] if win else flip[k["candidate_side"]]
            why = (f"{'candidate stronger' if win else 'lost'} "
                   f"vs {k['opponent_id']}")
        answers.append({"task_id": tid, "choice": choice, "why": why})
    if drop:
        answers = answers[:-drop]
    obj = {"schema": "cabinet.world.judge-results/v1",
           "run_id": run["run_id"], "answers": answers}
    if mutate:
        obj = mutate(obj)
    out = run_dir / "results.json"
    out.write_text(json.dumps(obj))
    return out


# ------------------------------------------------------------------- build

def test_build_bundle_shape_and_blinding(run_bundle):
    run_dir, run_doc, _, _ = run_bundle
    tasks_doc = json.loads((run_dir / "tasks.json").read_text())
    key_doc = json.loads((run_dir / "key.json").read_text())

    assert run_doc["counts"] == {"calibration": 10,
                                 "candidate_vs_positive": 5,
                                 "candidate_vs_negative": 2, "total": 17}
    assert len(tasks_doc["tasks"]) == 17
    # Runner-facing tasks carry NOTHING but the pair and the question.
    for t in tasks_doc["tasks"]:
        assert set(t) == {"id", "left", "right", "question"}
        assert re.fullmatch(r"images/img-[0-9a-f]{8}\.png", t["left"])
        assert re.fullmatch(r"images/img-[0-9a-f]{8}\.png", t["right"])
        assert t["left"] != t["right"]
        assert (run_dir / t["left"]).exists()
        assert "LEFT or RIGHT" in t["question"]
    # No ground-truth leak in the task array itself.
    blob = json.dumps(tasks_doc["tasks"])
    for label in ("pos-", "neg-", "cand", "calibration", "positive",
                  "negative", "corpus"):
        assert label not in blob
    # Key covers every task; both kinds are present and hidden-interleaved.
    assert set(key_doc["tasks"]) == {t["id"] for t in tasks_doc["tasks"]}
    kinds = [key_doc["tasks"][t["id"]]["kind"] for t in tasks_doc["tasks"]]
    assert set(kinds) == {"calibration", "candidate"}
    first, last = kinds.index("calibration"), len(kinds) - 1 - \
        kinds[::-1].index("calibration")
    assert any(k == "candidate" for k in kinds[first:last])  # interleaved


def test_build_randomizes_sides(run_bundle):
    run_dir, _, _, _ = run_bundle
    key = json.loads((run_dir / "key.json").read_text())["tasks"]
    cal_sides = {k["positive_side"] for k in key.values()
                 if k["kind"] == "calibration"}
    cand_sides = {k["candidate_side"] for k in key.values()
                  if k["kind"] == "candidate"}
    assert cal_sides == {"LEFT", "RIGHT"}  # position bias killed
    assert cand_sides == {"LEFT", "RIGHT"}


def test_build_deterministic_for_seed(tmp_path, judge, png):
    corpus = make_corpus(png, judge, tmp_path)
    cand = solid_png(png, tmp_path / "cand.png", 8, 8, (240, 180, 40, 255))
    d1, _ = judge.judge_protocol.build_run(
        [cand], corpus_dir=corpus, out_root=tmp_path / "r1", seed=77)
    d2, _ = judge.judge_protocol.build_run(
        [cand], corpus_dir=corpus, out_root=tmp_path / "r2", seed=77)
    t1 = json.loads((d1 / "tasks.json").read_text())
    t2 = json.loads((d2 / "tasks.json").read_text())
    k1 = json.loads((d1 / "key.json").read_text())
    k2 = json.loads((d2 / "key.json").read_text())
    assert t1["tasks"] == t2["tasks"]
    assert k1["tasks"] == k2["tasks"]
    assert k1["images"] == k2["images"]


def test_build_refuses_tampered_corpus(tmp_path, judge, png):
    corpus = make_corpus(png, judge, tmp_path)
    solid_png(png, corpus / "positive" / "pos-0.png", 8, 8, (1, 2, 3, 255))
    cand = solid_png(png, tmp_path / "cand.png", 8, 8, (240, 180, 40, 255))
    with pytest.raises(judge._corpus.CorpusError, match="hash mismatch"):
        judge.judge_protocol.build_run(
            [cand], corpus_dir=corpus, out_root=tmp_path / "runs", seed=1)


# ------------------------------------------------- aggregation + verdicts

def test_verdict_boundaries(judge):
    v = judge.judge_protocol.verdict_for
    assert v(1.0, 0.5) == "promote"       # holds its own vs the bar
    assert v(1.0, 1.0) == "promote"
    assert v(1.0, 0.49) == "iterate"      # clears negatives, below bar
    assert v(1.0, 0.0) == "iterate"
    assert v(0.99, 1.0) == "reject"       # any loss to a known-bad frame
    assert v(0.0, 1.0) == "reject"
    assert v(0.6, 0.6, neg_floor=0.5) == "promote"  # floor configurable


def test_ingest_promote(run_bundle, judge):
    run_dir, _, _, _ = run_bundle
    results = author_results(run_dir, pos_wins=3)  # 3/5 pos, 2/2 neg
    doc, code = judge.judge_protocol.ingest_run(run_dir, results)
    assert code == 0 and doc["status"] == "ok"
    cand = doc["candidates"][0]
    assert cand["win_rate_vs_negative"] == 1.0
    assert cand["win_rate_vs_positive"] == pytest.approx(0.6)
    assert cand["verdict"] == "promote"
    assert (run_dir / "verdicts.json").exists()
    assert doc["calibration"]["passed"] is True
    assert doc["calibration"]["n_pairs"] == 10


def test_ingest_iterate_and_notes(run_bundle, judge):
    run_dir, _, _, _ = run_bundle
    results = author_results(run_dir, pos_wins=2)  # 2/5 pos = 0.4
    doc, code = judge.judge_protocol.ingest_run(run_dir, results)
    cand = doc["candidates"][0]
    assert code == 0 and cand["verdict"] == "iterate"
    notes = cand["notes"]
    assert len(notes["losses_vs_positives"]) == 3
    assert len(notes["wins_vs_positives"]) == 2
    assert notes["losses_vs_negatives"] == []
    assert all(n["why"].startswith("lost vs")
               for n in notes["losses_vs_positives"])
    assert all(n["opponent"].startswith("pos-")
               for n in notes["losses_vs_positives"])


def test_ingest_reject_on_single_negative_loss(run_bundle, judge):
    run_dir, _, _, _ = run_bundle
    results = author_results(run_dir, pos_wins=None, neg_wins=1)  # 1/2 neg
    doc, code = judge.judge_protocol.ingest_run(run_dir, results)
    cand = doc["candidates"][0]
    assert code == 0 and cand["verdict"] == "reject"
    assert cand["win_rate_vs_negative"] == pytest.approx(0.5)
    assert cand["win_rate_vs_positive"] == 1.0  # pos wins cannot save it
    assert len(cand["notes"]["losses_vs_negatives"]) == 1


def test_ingest_void_uncalibrated(run_bundle, judge):
    run_dir, _, _, _ = run_bundle
    results = author_results(run_dir, cal_wrong=2)  # 8/10 = 0.8 < 0.9
    doc, code = judge.judge_protocol.ingest_run(run_dir, results)
    assert code == 1 and doc["status"] == "void_uncalibrated"
    assert doc["calibration"]["accuracy"] == pytest.approx(0.8)
    assert doc["calibration"]["passed"] is False
    assert len(doc["calibration"]["failures"]) == 2
    # No candidate verdict may leak out of a void run.
    assert doc["candidates"] == [{"candidate_id": "cand-1",
                                  "file": doc["candidates"][0]["file"],
                                  "verdict": "void"}]
    written = json.loads((run_dir / "verdicts.json").read_text())
    assert written["status"] == "void_uncalibrated"  # stamped


def test_ingest_calibration_boundary_exactly_90pct(run_bundle, judge):
    run_dir, _, _, _ = run_bundle
    results = author_results(run_dir, cal_wrong=1)  # 9/10 = 0.90 exactly
    doc, code = judge.judge_protocol.ingest_run(run_dir, results)
    assert code == 0 and doc["status"] == "ok"
    assert doc["calibration"]["accuracy"] == pytest.approx(0.9)
    assert doc["calibration"]["passed"] is True


def test_ingest_incomplete_is_void(run_bundle, judge):
    run_dir, _, _, _ = run_bundle
    results = author_results(run_dir, drop=1)
    doc, code = judge.judge_protocol.ingest_run(run_dir, results)
    assert code == 1 and doc["status"] == "void_incomplete"
    assert len(doc["missing_answers"]) == 1
    assert doc["candidates"][0]["verdict"] == "void"
    assert "calibration" in doc  # stamped even when incomplete


@pytest.mark.parametrize("mutate,label", [
    (lambda o: o | {"answers": o["answers"] + [o["answers"][0]]}, "dup"),
    (lambda o: o | {"answers": [o["answers"][0] | {"task_id": "t-zzz"}]
                    + o["answers"][1:]}, "unknown-id"),
    (lambda o: o | {"answers": [o["answers"][0] | {"choice": "MAYBE"}]
                    + o["answers"][1:]}, "bad-choice"),
    (lambda o: o | {"run_id": "jr-other"}, "run-mismatch"),
    (lambda o: {"not_answers": []}, "bad-shape"),
])
def test_ingest_malformed_results_exit2(run_bundle, judge, mutate, label):
    run_dir, _, _, _ = run_bundle
    results = author_results(run_dir, mutate=mutate)
    code = judge.judge_protocol.main(
        ["ingest", "--run", str(run_dir), "--results", str(results)])
    assert code == 2, label
    assert not (run_dir / "verdicts.json").exists()  # nothing scored


def test_ingest_cli_exit_codes(run_bundle, judge):
    run_dir, _, _, _ = run_bundle
    ok = author_results(run_dir)
    assert judge.judge_protocol.main(
        ["ingest", "--run", str(run_dir), "--results", str(ok)]) == 0
    void = author_results(run_dir, cal_wrong=3)
    assert judge.judge_protocol.main(
        ["ingest", "--run", str(run_dir), "--results", str(void)]) == 1


# -------------------------------------------------------- calibration lib

def test_calibration_full_cross_product_and_cap(judge):
    import random
    pos = [{"id": f"p{i}"} for i in range(5)]
    neg = [{"id": f"n{i}"} for i in range(2)]
    pairs = judge.calibration.build_pairs(pos, neg, random.Random(1))
    assert len(pairs) == 10
    assert {(p["positive"]["id"], p["negative"]["id"])
            for p in pairs} == {(f"p{i}", f"n{j}")
                                for i in range(5) for j in range(2)}
    capped = judge.calibration.build_pairs(pos, neg, random.Random(1),
                                           max_pairs=4)
    assert len(capped) == 4
    with pytest.raises(ValueError):
        judge.calibration.build_pairs([], neg, random.Random(1))


def test_calibration_score_missing_answer_counts_incorrect(judge):
    key = [{"task_id": "t-1", "positive_side": "LEFT",
            "positive_id": "p", "negative_id": "n"},
           {"task_id": "t-2", "positive_side": "RIGHT",
            "positive_id": "p", "negative_id": "n"}]
    res = judge.calibration.score(key, {"t-1": {"choice": "LEFT",
                                                "why": ""}})
    assert res["correct"] == 1 and res["accuracy"] == 0.5
    assert res["passed"] is False
    assert res["failures"][0]["task_id"] == "t-2"
    assert res["failures"][0]["chose"] is None
    empty = judge.calibration.score([], {})
    assert empty["passed"] is False  # zero pairs can never calibrate


# ----------------------------------------------------------------- goldens

def _checker(png, path: Path, w=32, h=32, block=4,
             a=(230, 210, 170, 255), b=(60, 80, 120, 255)) -> Path:
    px = bytearray()
    for y in range(h):
        for x in range(w):
            px += bytes(a if ((x // block) + (y // block)) % 2 == 0 else b)
    path.parent.mkdir(parents=True, exist_ok=True)
    png.encode(path, w, h, bytes(px))
    return path


def test_golden_pin_and_identical_compare(tmp_path, judge, png):
    gdir = tmp_path / "goldens"
    frame = _checker(png, tmp_path / "frame.png")
    entry = judge.goldens.pin_golden(frame, "wardroom-z2", note="approved",
                                     goldens_dir=gdir)
    assert entry["size"] == [32, 32]
    assert (gdir / "wardroom-z2.png").exists()
    result = judge.goldens.compare_to_golden(frame, "wardroom-z2",
                                             goldens_dir=gdir)
    assert result["pass"] is True
    assert result["regions"][0]["ssim"] == pytest.approx(1.0)
    assert result["regions"][0]["pixel_diff_frac"] == 0.0
    # re-pin without --force is refused (ratchet, not a mutable slot)
    with pytest.raises(judge.goldens.GoldenError, match="--force"):
        judge.goldens.pin_golden(frame, "wardroom-z2", goldens_dir=gdir)


def test_golden_per_region_thresholds_localize_failure(tmp_path, judge, png):
    gdir = tmp_path / "goldens"
    frame = _checker(png, tmp_path / "frame.png")
    judge.goldens.pin_golden(
        frame, "scene", goldens_dir=gdir,
        regions=[{"name": "quiet", "rect": [0, 0, 16, 16]},
                 {"name": "hot", "rect": [16, 16, 16, 16]}])
    # corrupt an 8x8 block inside "hot" only
    w, h, rgba = png.decode(frame)
    buf = bytearray(rgba)
    for y in range(20, 28):
        for x in range(20, 28):
            i = (y * w + x) * 4
            buf[i:i + 3] = bytes((255 - buf[i], 255 - buf[i + 1],
                                  255 - buf[i + 2]))
    cand = tmp_path / "cand.png"
    png.encode(cand, w, h, bytes(buf))

    result = judge.goldens.compare_to_golden(cand, "scene", goldens_dir=gdir)
    by_name = {r["name"]: r for r in result["regions"]}
    assert by_name["quiet"]["pass"] is True
    assert by_name["quiet"]["pixel_diff_frac"] == 0.0
    assert by_name["hot"]["pass"] is False
    assert by_name["hot"]["pixel_diff_frac"] == pytest.approx(64 / 256)
    assert by_name["hot"]["ssim"] < by_name["quiet"]["ssim"]
    assert result["pass"] is False
    code = judge.goldens.main(["compare", "--image", str(cand),
                               "--golden", "scene",
                               "--goldens-dir", str(gdir)])
    assert code == 1


def test_golden_tamper_and_size_mismatch(tmp_path, judge, png):
    gdir = tmp_path / "goldens"
    frame = _checker(png, tmp_path / "frame.png")
    judge.goldens.pin_golden(frame, "scene", goldens_dir=gdir)
    # size mismatch -> regression fail (exit 1), reported not crashed
    small = _checker(png, tmp_path / "small.png", w=16, h=16)
    result = judge.goldens.compare_to_golden(small, "scene",
                                             goldens_dir=gdir)
    assert result["pass"] is False and "size mismatch" in result["error"]
    # tampered golden bytes -> integrity refusal (exit 2)
    _checker(png, gdir / "scene.png", a=(1, 1, 1, 255))
    with pytest.raises(judge.goldens.GoldenError, match="drifted"):
        judge.goldens.compare_to_golden(frame, "scene", goldens_dir=gdir)
    assert judge.goldens.main(["compare", "--image", str(frame),
                               "--golden", "scene",
                               "--goldens-dir", str(gdir)]) == 2
    assert judge.goldens.verify_goldens(gdir) != []


def test_record_verdict_accumulates_taste(tmp_path, judge, png):
    corpus = make_corpus(png, judge, tmp_path, n_pos=2, n_neg=1)
    good = solid_png(png, tmp_path / "good.png", 8, 8, (250, 220, 120, 255))
    bad = solid_png(png, tmp_path / "bad.png", 8, 8, (20, 20, 20, 255))

    e1 = judge.goldens.record_verdict(good, "approve", "warm and grounded",
                                      entry_id="cap-a1", corpus_dir=corpus)
    e2 = judge.goldens.record_verdict(bad, "reject", "flat void again",
                                      entry_id="cap-r1", corpus_dir=corpus)
    assert e1["class"] == "positive" and e2["class"] == "negative"
    assert (corpus / "positive" / "cap-a1.png").exists()
    assert (corpus / "negative" / "cap-r1.png").exists()

    data = json.loads((corpus / "manifest.json").read_text())
    assert data["counts"] == {"positive": 3, "negative": 2}
    by_id = {i["id"]: i for i in data["images"]}
    assert by_id["cap-a1"]["why"] == "warm and grounded"
    assert by_id["cap-a1"]["sha256"] == judge._corpus.sha256_of(good)
    # the accumulated corpus is immediately judgeable
    entries = judge._corpus.corpus_entries("positive", corpus)
    assert {e["id"] for e in entries} == {"pos-0", "pos-1", "cap-a1"}

    with pytest.raises(judge.goldens.GoldenError, match="already exists"):
        judge.goldens.record_verdict(good, "approve", "dup",
                                     entry_id="cap-a1", corpus_dir=corpus)
    with pytest.raises(judge.goldens.GoldenError, match="--note"):
        judge.goldens.record_verdict(good, "approve", "   ",
                                     corpus_dir=corpus)


def test_ssim_and_pixel_diff_units(judge):
    g = judge.goldens
    flat_a = [128] * 64
    assert g.ssim_region(flat_a, list(flat_a), 8, (0, 0, 8, 8)) == \
        pytest.approx(1.0)
    black, white = [0] * 64, [255] * 64
    assert g.ssim_region(black, white, 8, (0, 0, 8, 8)) < 0.01
    a = bytes((10, 20, 30, 255)) * 16
    b = bytearray(a)
    b[0] = 200  # one pixel differs in a 4x4 region
    assert g.pixel_diff_frac(a, bytes(b), 4, (0, 0, 4, 4)) == \
        pytest.approx(1 / 16)
    assert g.pixel_diff_frac(a, a, 4, (0, 0, 4, 4)) == 0.0


# --------------------------------------- build_corpus.py carries verdicts

def test_build_corpus_manifest_preserves_recorded_entries(
        tmp_path, judge, png, monkeypatch, capsys):
    corpus = make_corpus(png, judge, tmp_path, n_pos=1, n_neg=1)
    extra = solid_png(png, tmp_path / "extra.png", 8, 8, (5, 6, 7, 255))
    judge.goldens.record_verdict(extra, "approve", "captain liked it",
                                 entry_id="cap-keeper", corpus_dir=corpus)

    bc = _load("world_aesthetic_build_corpus_test",
               WA_DIR / "build_corpus.py")
    monkeypatch.setattr(bc, "HERE", tmp_path)
    monkeypatch.setattr(bc, "CORPUS", corpus)
    monkeypatch.setattr(bc, "MANIFEST", corpus / "manifest.json")
    monkeypatch.setattr(bc, "REGISTRY", {
        "pos-0": ("positive", "pos-0.png", "test prov", "test why"),
    })

    bc.build_manifest()
    data = json.loads((corpus / "manifest.json").read_text())
    ids = {i["id"] for i in data["images"]}
    assert "cap-keeper" in ids          # Captain taste survives a rebuild
    assert "pos-0" in ids               # REGISTRY entry rebuilt
    assert "neg-0" in ids               # non-REGISTRY fixture entry carried
    assert data["counts"] == {"positive": 2, "negative": 1}

    # a drifted carried file is a hard stop, never a silent drop
    solid_png(png, corpus / "positive" / "cap-keeper.png",
              8, 8, (99, 99, 99, 255))
    with pytest.raises(SystemExit):
        bc.build_manifest()
