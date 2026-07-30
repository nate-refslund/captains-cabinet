# Review — `fix/display-names-any-script` cp1

Self-review of the diff, written after attacking it rather than after reading
it. Every claim below carries the command that produced it, run on this branch.

Scope: `cabinet/scripts/generate-instance.py`,
`presets/portfolio/agents/_lane-ceo.md.template`,
`cabinet/scripts/tests/test_generate_instance.py`,
`.claude/skills/cabinet-init/SKILL.md`.

---

## 1. What the change actually does

`NAME_RE = ^[A-Za-z0-9][A-Za-z0-9 &+._/()-]{0,79}$` is deleted. It gated three
display-name fields (`captain.name`, each lane `name`, `--captain-name`) and
was standing in for two constraints, neither of them an alphabet:

| the old rule was really enforcing | where it now lives |
|---|---|
| a length cap | `DISPLAY_NAME_MAX = 80`, unchanged, counted in characters |
| "it is written into YAML scalars" (its own error hint said so) | `_yaml_str` / `_yaml_dq_inner` at EMISSION, plus a round-trip assertion |

`cabinet.id` and lane `slug` keep ASCII kebab-case — they key file names,
session names and log lines, which is a real constraint — but their refusal is
no longer a raw regex.

### NAME_RE call sites, enumerated and each handled deliberately

`git grep -n "NAME_RE" cabinet/scripts/generate-instance.py` on origin/master
returned 8 lines; **5 were call sites**, 3 were the definition and docstrings.

| # | line (pre) | field | verdict |
|---|---|---|---|
| 1 | 389 | `captain.name` | DISPLAY → `validate_display_name` |
| 2 | 502 | `lanes[i].name` | DISPLAY → `validate_display_name` |
| 3 | 1529 | `--captain-name` explicit | DISPLAY → `validate_display_name`; refuses loud, unchanged |
| 4 | 1536 | ambient `$USER` | DISPLAY → `validate_display_name`; falls back silently, unchanged |
| 5 | 1248-1249 | `_yaml_str` docstring asserting "every call site is NAME_RE-validated, and NAME_RE forbids `"` and `\`" | **the load-bearing one** — that assumption is why `_yaml_str` did no escaping. Removing the alphabet without fixing it would have shipped a broken quoted branch. |

`ENV_NAME_RE` (UPPER_SNAKE env var names) is a genuinely different field and is
untouched. `generate-plists.py` / `generate-services-cron.py` have their own
`NAME_RE`s over service names (`^[a-z0-9-]+$`) — identifiers, not display
names, out of scope.

---

## 2. Attack pass — the part that found something

`python3.12 scratchpad/attack_pass.py` drives the **full generator** (not a
helper) with 49 hostile display names — YAML indicators at every position,
document separators, type-coercion bait, combining marks, RTL marks, ZWJ,
NBSP, and eight scripts — and asserts each name comes back out of all five
artifacts byte-identically.

```
hostile display names probed : 49
round-trip failures/refusals : 0
```

First run found **1 failure**, and it was real:

> **FINDING (fixed in this diff, pre-existing on master).** The agent-frontmatter
> validator used `content.split("---", 2)[1]` — a SUBSTRING split — at three
> call sites. Any `---` inside the frontmatter ends the slice early.
> `Ada --- Prime` passes the OLD `NAME_RE` too (`-` and ` ` are both in its
> class), and on master it makes the validator parse the fragment
> `description: Lane CEO for Ada ` — which is valid YAML, so the gate reported
> the file valid **having read half of it**. Verified on a pristine master copy:
> generation succeeds, validation is silently partial. A validator that fails
> open is worse than the parse error the same input produces once the scalar is
> quoted. Fixed by `_frontmatter_text()`, which matches delimiter LINES, wired
> into all three sites; pinned by
> `test_frontmatter_extraction_survives_a_dashed_name`, which asserts the keys
> after `description:` survive.

That is the one class the change had to be attacked to find: the diff reads
fine, and this only shows up when you feed the emission path something it was
previously protected from by the input rule you just removed.

---

## 3. Attacks that did NOT find anything, and why I believe them

**"Safe emission is a claim; prove it at the position the scalar occupies."**
`_yaml_str`'s old test parsed the value as a whole DOCUMENT — a different
grammar context from a mapping value. Replaced with a probe in the position
it will occupy (`k: <value>` must load as `{"k": value}`). I then checked the
other two indentations the function serves — `product.name` at indent 2,
`roster.<slug>.title` at indent 4 — against the worst case found by the attack
pass (`--- name`) and all three agree. Block-context plain scalars do not
change legality with indentation depth; the failing case was the extractor, not
the probe.

**"The quoted branch escapes nothing."** It did not — `f'"{value}"'` — and the
docstring said that was safe *because NAME_RE forbids quotes and backslashes*.
That is now `json.dumps(..., ensure_ascii=False)`, the same primitive
`_yaml_free` already used for free text since egg-hatch-engine-5.
`ensure_ascii=False` is deliberate: a `\uXXXX` soup would parse correctly and
still tell the operator the product could not cope with their name.

**"Does anything downstream crash on a non-ASCII name?"** Two shell readers
take `captain_name` with `awk '{print $2}'`
(`cabinet/scripts/hooks/post-tool-use.sh:689`, `assemble-config.sh:60`). They
truncate at the first space — but they already did that to `Ada Lovelace`, and
NAME_RE always allowed spaces. `_yaml_str` keeps plain names BARE precisely so
those greppers see what they saw before; the CJK case behaves exactly like the
multi-word ASCII case. Not a regression, and not silently accepted: it is
written down here. `bootstrap-roles.sh`'s roster awk strips surrounding quotes
(`gsub(/^"|"$/, "", val)`), so a quoted `title:` degrades to a slightly
escaped display string rather than a parse failure. `framework/env.py`
`captain_name()` reads through PyYAML and is exact.

**"Did the secret guard get weaker?"** No. `_scan_for_secrets` runs over the
whole answers mapping BEFORE any field validation, so it still sees display
names. Pinned by `test_secret_shaped_names_still_refused`, which is one of the
three arms that pass on BOTH sides of the change — correctly, since it is a
regression pin, not a proof of the change.

**"Did the identifier rule get widened by accident?"**
`test_identifiers_still_refuse_path_escapes` re-runs the whole path-escape
corpus (`../evil`, `/abs/path`, `a/b`, `a.b`, `UPPER`, `..`, `x x`) through the
NEW message path. `SLUG_RE` itself is byte-unchanged.

**"Are control characters actually gone, or just newline?"** The refusal is
Unicode category Cc plus U+2028/U+2029, so NUL, tab, NEL and the line/paragraph
separators are all refused — the last three because YAML treats them as line
breaks and PyYAML would re-line the file. Format characters (Cf: ZWJ, ZWNJ,
RLM, LRM) are deliberately NOT refused: they are load-bearing in Arabic, Hebrew
and Indic scripts, and a blanket "invisible characters" ban would re-create
this exact defect one script down. Pinned in both directions
(`test_control_characters_still_refused`, `test_format_characters_are_not_refused`).

---

## 4. Weakest points in this diff

Stated plainly rather than left for a reviewer to find.

1. **The lane-CEO template's `description:` is now a quoted scalar.** That is a
   preset file, and quoting it is what makes mid-sentence substitution safe.
   The template says why in a comment right above it, and unquoting it breaks
   `test_yaml_structural_characters_are_escaped_not_banned`. But it is a
   coupling between a preset file and a generator function, and nothing except
   that test enforces it.
2. **`render_agent` now substitutes in two regions** (escaped in the
   frontmatter, verbatim in the body). If a future placeholder is added to the
   frontmatter that must NOT be escaped, the split will quietly escape it.
   `_yaml_dq_inner` is a no-op for every current placeholder value
   (`lane-a-ceo`, `claude-opus-4-8[1m]`, repo lists), so today it is invisible —
   which is exactly what makes it a future trap. Named here on purpose.
3. **The round-trip assertion checks the five artifacts it knows about.** A
   sixth emission site added later gets no coverage automatically. It is keyed
   off `outputs`, so it will at least SEE the new artifact, but it will not
   assert anything about it.
4. **The `--- name` finding was pre-existing and silent.** I fixed the
   extractor, but I did not audit every other `split("---"` in the repo. Out of
   scope for this branch; worth a sweep.
5. **`test_default_captain_name_resolution` had two arms retargeted.**
   `bad:name` / `bad:user` were asserting the ALPHABET, which no longer exists;
   keeping them would have meant either failing the suite or reverting the
   change. They now carry values that are unusable for reasons that are still
   real (control char, empty, over-length). This is a deliberate contract
   change, recorded in the test's own docstring, not a test bent to fit.

---

## 5. Evidence

| claim | command | result |
|---|---|---|
| new tests FAIL against pre-change code | `bash scratchpad/prechange_proof.sh` (pristine `generate-instance.py` + template restored, `__pycache__` purged, `PYTHONDONTWRITEBYTECODE=1`) | 26 failed, 3 passed — the 3 are the regression pins (ASCII byte-identity, `""` required-field, secret sweep), which MUST pass on both sides |
| the exact measured defect | same run | `GenerationError: captain.name '高橋 美咲' must match ^[A-Za-z0-9][A-Za-z0-9 &+._/()-]{0,79}$ (plain display name)` |
| pre-change acceptance rate | `NAME_RE.match` over the 49 attack names | 42 of 49 refused |
| post-change round-trip | `python3.12 scratchpad/attack_pass.py` | 49 probed, 0 failures |
| generator suite | `python3.12 -m pytest cabinet/scripts/tests/test_generate_instance.py -q` | 162 passed |
| CI battery 1 | `python3.12 -m pytest cabinet/scripts/tests -q` | 5151 passed, 34 skipped |
| CI battery 2 | `python3.12 -m pytest framework/ -q -rs` | 1 failed, 7806 passed — `framework/fidelity/tests/test_retro_shim.py::test_reexports_constants`, a model-id constant mismatch, **reproduced on pristine origin/master (363c9fa2)**, unrelated to this diff |
| layer separation | `bash cabinet/scripts/check-layer-separation.sh` | `new=0` |
| docs track code | `bash cabinet/scripts/docs-track-code-sweep.sh` | `GREEN (files=64 findings=0)` |
| guarded tokens in diff | `git diff -U0 \| grep -Ei "killswitch\|never-a-score\|observe-only\|veto"` | 0 hits |

`pytest cabinet/scripts/tests framework/tests` in ONE invocation reports 31
collection errors — **on origin/master too**, verified against a clean clone.
Both trees expose an un-packaged top-level `tests` module; CI runs them as
separate steps and documents exactly this (`cabinet-ci.yml:908`). The two
commands above are what CI runs.

## 6. Doctrine this lands against

`framework/onboarding/salience.py`, retirement note RES-025: *"THE ALPHABET IS
THE UNICODE DATABASE, not `[0-9a-z]` … a name written in Japanese, Cyrillic,
Greek, Arabic, Hebrew, Hindi, Thai or Korean yielded no words on either side of
any comparison."* That was already landed. The generator was the last ASCII
gate in the onboarding path, and it sat at the very first question the product
asks anyone.
