#!/usr/bin/env python3
"""cabinet/scripts/meta-cognition/similarity.py

Keyword-overlap scorer shared by the meta-cognition layers (Layer 1 encode-gate
and Layer 2 harvester). Given a candidate rule text and a corpus markdown file
(the existing patterns/principles), find the existing heading whose heading +
excerpt-zone body best COVERS the candidate's salient keywords.

"Covers" = overlap coefficient (intersection / |candidate tokens|) — robust to a
long existing body, where raw Jaccard dilutes. This measures "how much of the
candidate is already encoded in a single existing principle", which is exactly
the anti-accretion question.

Prints "<best heading>\t<overlap 0..1>" to stdout when the best overlap clears
the floor AND at least 3 salient tokens are shared; prints nothing otherwise.
Exit 0 always.

Usage:
  similarity.py <candidate_text> <corpus.md> [floor]
  echo <candidate> | similarity.py - <corpus.md> [floor]

Env: META_OVERLAP_FLOOR overrides the default 0.50 floor (CLI arg wins if given).
No deps (stdlib only). No network. Read-only on the corpus file.
"""
from __future__ import annotations

import os
import re
import sys

STOP = set(
    """a an the and or but if then of to in on for with as is are be it this that
    these those we you i they our your their not no do does did can will shall
    should would could about into over under than from at by per via vs so just
    only also any all each new rule when before after onto every always never
    officer cabinet captain must may make made get got use used""".split()
)


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    return {w for w in words if w not in STOP}


def best_cover(candidate: str, corpus_path: str) -> tuple[float, str]:
    cand = tokens(candidate)
    if len(cand) < 3 or not os.path.exists(corpus_path):
        return (0.0, "")
    with open(corpus_path) as fh:
        text = fh.read()
    heads = list(re.finditer(r"^#{2,3}\s+(.*)$", text, re.MULTILINE))
    best = (0.0, "")
    for i, h in enumerate(heads):
        title = h.group(1).strip()
        start = h.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[start:end][:400]
        existing = tokens(title + " " + body)
        if not existing:
            continue
        inter = len(cand & existing)
        overlap = inter / len(cand) if cand else 0.0
        if overlap > best[0] and inter >= 3:
            best = (overlap, title)
    return best


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 0
    candidate = argv[1]
    if candidate == "-":
        candidate = sys.stdin.read()
    corpus_path = argv[2]
    floor = float(argv[3]) if len(argv) > 3 else float(
        os.environ.get("META_OVERLAP_FLOOR", "0.50")
    )
    score, title = best_cover(candidate, corpus_path)
    if score >= floor and title:
        sys.stdout.write(f"{title}\t{score:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
