"""deploy-mac.sh: one bootout-first retry before the per-service rollback.

WHY (2026-08-12). A real operator's hatch died at ``deploy-mac.sh --officer
cos`` with launchd's ``Bootstrap failed: 5: Input/output error``. Error 5 is
launchd's catch-all and its commonest meaning is "that label is already
loaded". ``install_plist_file`` only booted the label out when its
``launchctl print`` probe said the job was loaded — so whenever the probe and
reality disagreed, the bootstrap hit an existing job and hard-failed. hatch.sh's
own plist loader has done an UNCONDITIONAL bootout-first since it was written,
with a comment naming this exact error; the officer leg went through here and
did not. This closes that asymmetry.

The retry is strictly ADDITIVE on the already-failing path: a bootstrap that
succeeds first time never reaches it, so no currently-working deploy changes.

HERMETIC: ``install_plist_file`` + ``wait_for_unloaded`` are extracted from the
real script by literal marker and driven against a FAKE ``launchctl``
(``$LAUNCHCTL``, the script's own seam) that models launchd's behaviour —
bootstrap refuses while a label is "loaded", bootout unloads it. No real
launchd domain is read or touched.

Run: python3.12 -m pytest cabinet/scripts/tests/test_deploy_mac_bootout_retry.py -q
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "cabinet" / "scripts" / "deploy-mac.sh"

_START = "ensure_deploy_tmp() {"
_END = "render_template() {"
_LABEL = "com.cabinet.officer.cos"
_EIO = "Bootstrap failed: 5: Input/output error"


def _slice() -> str:
    text = _SCRIPT.read_text(encoding="utf-8")
    assert _START in text, "deploy-mac.sh lost the ensure_deploy_tmp marker"
    body = text[text.index(_START):]
    assert _END in body, "deploy-mac.sh lost the render_template marker"
    return body[: body.index(_END)]


def _fake_launchctl(tmp: Path, *, loaded: bool, print_sees_it: bool,
                    bootout_works: bool = True) -> Path:
    """A launchd model in ~30 lines.

    ``loaded``          the label really IS loaded in the domain.
    ``print_sees_it``   whether `launchctl print` admits that. The operator's
                        failure is the (True, False) cell: really loaded, probe
                        says no, so the caller skips its conditional bootout.
    """
    state = tmp / "loaded"
    state.write_text("1" if loaded else "", encoding="utf-8")
    log = tmp / "launchctl.log"
    fake = tmp / "launchctl"
    fake.write_text(f"""#!/bin/bash
echo "$@" >> "{log}"
verb="$1"
is_loaded() {{ [ -s "{state}" ]; }}
case "$verb" in
  print)
    if is_loaded && [ "{int(print_sees_it)}" = "1" ]; then exit 0; fi
    exit 1 ;;
  bootout)
    if [ "{int(bootout_works)}" != "1" ]; then exit 1; fi
    : > "{state}"; exit 0 ;;
  bootstrap)
    if is_loaded; then echo "{_EIO}" >&2; exit 5; fi
    printf '1' > "{state}"; exit 0 ;;
esac
exit 0
""", encoding="utf-8")
    fake.chmod(0o755)
    return log


def _drive(tmp_path: Path, *, loaded: bool, print_sees_it: bool,
           bootout_works: bool = True, had_final: bool = True):
    tmp = tmp_path / "fake"
    tmp.mkdir()
    log = _fake_launchctl(tmp, loaded=loaded, print_sees_it=print_sees_it,
                          bootout_works=bootout_works)
    src = tmp_path / "new.plist"
    src.write_text("<plist>new</plist>\n", encoding="utf-8")
    final = tmp_path / "installed.plist"
    if had_final:
        final.write_text("<plist>old</plist>\n", encoding="utf-8")

    script = tmp_path / "drive.sh"
    script.write_text(
        "#!/bin/bash\n"
        "set -uo pipefail\n"
        f'LAUNCHCTL="{tmp / "launchctl"}"\n'
        "BOOTOUT_DELAY_S=0\n"
        'DEPLOY_TMP=""\n'
        + _slice()
        + f'\ninstall_plist_file "{src}" "{final}" "{_LABEL}"\n'
        "echo \"rc=$?\"\n",
        encoding="utf-8",
    )
    p = subprocess.run(["/bin/bash", str(script)], capture_output=True,
                       text=True, timeout=60)
    calls = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return p, calls, final


def _verbs(calls: list[str]) -> list[str]:
    return [c.split()[0] for c in calls]


# ---------------------------------------------------------------------------
# The operator's cell: really loaded, `print` does not see it
# ---------------------------------------------------------------------------

def test_stale_probe_no_longer_hard_fails_the_deploy(tmp_path):
    p, calls, final = _drive(tmp_path, loaded=True, print_sees_it=False)
    assert "rc=0" in p.stdout, (
        "a bootstrap that failed only because the label was already loaded "
        "must recover, not fail the deploy", p.stdout, p.stderr,
    )
    assert "after a bootout-first retry" in p.stdout, (
        "the recovery must say so — a silent retry hides a real fragility"
    )
    # bootstrap, EIO, unconditional bootout, bootstrap again
    assert _verbs(calls) == ["print", "bootstrap", "bootout", "print", "bootstrap"], _verbs(calls)
    # the NEW plist is what stayed installed
    assert final.read_text(encoding="utf-8") == "<plist>new</plist>\n"


def test_happy_path_never_reaches_the_retry(tmp_path):
    """Additive-only: a first-time bootstrap must be untouched by this."""
    p, calls, _final = _drive(tmp_path, loaded=False, print_sees_it=False)
    assert "rc=0" in p.stdout, (p.stdout, p.stderr)
    assert "after a bootout-first retry" not in p.stdout
    assert _verbs(calls) == ["print", "bootstrap"], _verbs(calls)


def test_correctly_probed_reload_is_unchanged(tmp_path):
    """Loaded AND seen: the pre-existing conditional bootout handles it, and
    the retry never fires."""
    p, calls, _final = _drive(tmp_path, loaded=True, print_sees_it=True)
    assert "rc=0" in p.stdout, (p.stdout, p.stderr)
    assert "after a bootout-first retry" not in p.stdout
    assert _verbs(calls) == ["print", "bootout", "print", "bootstrap"], _verbs(calls)


def test_a_genuinely_broken_bootstrap_still_fails_and_rolls_back(tmp_path):
    """The retry must not paper over a real failure. Bootout cannot clear the
    label here, so both bootstraps fail — the rollback runs exactly as before
    and the previous plist is restored."""
    p, calls, final = _drive(tmp_path, loaded=True, print_sees_it=False,
                             bootout_works=False)
    assert "rc=2" in p.stdout, ("a bootstrap that cannot be recovered must "
                               "still fail", p.stdout, p.stderr)
    assert "attempting per-service rollback" in p.stderr
    assert _verbs(calls).count("bootstrap") <= 3, (
        "the retry is ONE extra attempt, never a loop", _verbs(calls),
    )
    assert final.read_text(encoding="utf-8") == "<plist>old</plist>\n", (
        "the previous plist must be restored on an unrecoverable failure"
    )


def test_retry_is_wired_between_the_first_bootstrap_and_the_rollback():
    """Source pin: the drives above cannot see the retry being moved after the
    rollback, where it would fire on a restored plist."""
    body = _slice()
    first = body.index('if "$LAUNCHCTL" bootstrap')
    retry = body.index('bootout "gui/$(id -u)" "$final" 2>/dev/null || true',
                       first)
    rollback = body.index("attempting per-service rollback")
    assert first < retry < rollback, (
        "the bootout-first retry must sit between the first bootstrap and the "
        "rollback"
    )
