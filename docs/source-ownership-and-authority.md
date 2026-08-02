# Whose data is this?

Every source your cabinet reads or writes carries an **ownership class** and an
**authority basis**. This page says what those are, what the cabinet does with
them, and — the part most such pages leave out — what it **cannot** do.

## Why the question exists

Connecting a system to an autonomous agent is an authorization decision. If you
run your own company, it is yours to make. If you work at a large one, most of
the systems on your laptop belong to your employer: the tracker, the repo, the
drive, the mail. Pointing an agent at them is a decision you do not hold alone,
and an agent that quietly assumed otherwise would be making it for you.

So the cabinet asks, once per source, and refuses to proceed until you answer.

## The three classes

| Class | What it means | Reads | Writes | Content leaving the machine |
|---|---|---|---|---|
| `self` | Your own estate. You are the authority over it. | yes | yes | allowed |
| `employer` | Your employer's. You hold a seat in it. | yes | **refused** | allowed, and recorded |
| `third_party` | A client's, customer's, counterparty's. | yes | **refused** | **per-item approval** |

Reads are allowed for all three on purpose. Reading a tracker you have a seat in
is the whole point of the product at employee altitude, and refusing it would be
safety theatre that costs the feature without protecting anyone.

Writes are where the asymmetry sits. A write to a system you do not own changes
somebody else's record — a colleague's ticket, a client's board — and the undo
window does not help, because undoing a write to a colleague's ticket does not
un-notify the colleague.

Egress is graded rather than binary. Summarizing your own view of your
employer's repo back to you is the product; shipping a client's words to a
messaging service they never agreed to is the exposure. So `employer` content
moves with a record and `third_party` content waits for your approval, item by
item.

## Unclassified is refused, never defaulted

If you cannot classify a source, the cabinet does not read it and does not
connect to it. It does not fall back to the safest-looking class, because a
default is the cabinet answering the question on your behalf, which is the exact
thing this gate exists to prevent. The refusal is recorded with a reason, like
every other refusal.

The same rule applies to old data: content with no recorded class is treated as
the **strictest** case, not the loosest.

## What the cabinet refuses to read at all

Beyond credentials — which it has always skipped — the First Window refuses
whole categories by name, and records each refusal under the category it
refused:

`credentials` · `personnel` · `compensation` · `customer_pii` · `legal` ·
`corporate_finance`

Those are the categories that get someone fired. The detectors read file and
folder NAMES, not contents, and they are deliberately narrow: a detector that
fires on ordinary working documents gets switched off within a week, and a
switched-off detector refuses nothing. A narrow detector will therefore miss
things — a payroll table in a file called `q3.xlsx` will be read. Do not treat
the refusal list as a guarantee that nothing sensitive was opened.

## The record outlives the read

Every completed read writes a record that survives, per source: the root, the
ownership class, the authority basis, the Charter and manifest fingerprints, how
many files were read, and **every refusal with its class and count**. Silent
skips would make the sweep unauditable, so nothing is skipped silently.

Deleting your onboarding data (`purge`) does not delete this record — it stamps
the purge receipt onto it and **redacts the folder path**, leaving the fingerprint
behind. You can erase what was read; the fact that a read happened, against whose
data and under what claimed right, stays. The record holds fingerprints and
counts, never file contents, so keeping it does not keep the data.

A record is stamped by the purge that redacted it and by no later one, so a
second journey's deletion cannot relabel the first read's audit link. The
purge dialog now says all of this before you type `PURGE`: what is destroyed,
what is kept, and that you can start a new orientation afterwards.

## What this CANNOT enforce

**The cabinet cannot verify that your answer is true.** Nothing stops you from
classifying your employer's tracker as `self` and getting full write access. No
software on your machine can check your employment contract, your client's data
processing agreement, or what your IT department actually permits.

What it can do, and does:

- force the question once per source, in plain words, before any read;
- refuse to proceed when the question is not answered;
- record the answer and the basis you gave, where the record survives the read;
- make the write half of anything you did not claim as your own **structurally**
  unreachable — a different code path, not a setting;
- default everything not claimed as yours to no-egress or approval-gated egress.

That is the enforceable boundary. Claiming more of it would be the same false
comfort as a default.

## Where this lives

- `framework/authority/ownership.py` — the classes, the refusals, the graded
  egress dispositions, the sensitivity classes, the access-record shape.
- `framework/onboarding/journey.py` — the ingest ceiling on the First Window;
  ownership is bound into the Charter fingerprint you approve.
- `cabinet/scripts/task_adapters/base.py` — structural read-only for any tracker
  you do not own.
- `instance/config/projects/_template.yml` — how to declare it for a tracker.
