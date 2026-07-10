<!-- Thanks for contributing. For anything non-trivial, an issue first —
     the design conversation happens before the diff (CONTRIBUTING.md,
     "Contribution flow"). -->

## What & why

<!-- What changes, and the problem it solves. Link the issue. -->

## Tests

<!-- The suites you ran and their results — paste the command + tail.
     "Run what you touched; CI runs all of it" (CONTRIBUTING.md → Test
     suites). New behavior needs new tests; a fix needs a test that fails
     without it. -->

```
python3 -m pytest <what you touched> -q
```

## Checklist

- [ ] Tests pass locally for the surfaces I touched.
- [ ] **Docs track the code**: every doc/runbook/README that names what I
      changed is updated in this same PR (grep the old name).
- [ ] Shell changes pass `bash -n` and `shellcheck --severity=error`.
- [ ] No germline path is edited or worked around (see CONTRIBUTING.md →
      Germline etiquette).
- [ ] **DCO sign-off**: every commit carries `Signed-off-by:` (`git commit -s`)
      — see the DCO section of CONTRIBUTING.md.
