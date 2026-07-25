"""framework.liveness — Captain-contact dead-man heartbeats (D1).

Every other health signal in this tree is produced AND consumed inside the same
failure domain, so the cabinet can only ever report on itself. This package is
the one exception: it emits a heartbeat at the moment CONTACT WITH THE CAPTAIN
actually happens, to a watcher that lives OFF this machine. Nothing here checks
anything — the alarm is the ABSENCE of the ping, raised by the external watcher.

That inversion is the whole point: the outage is the trigger, so the outage
cannot suppress the alarm. A launchd-scheduled check cannot make this claim,
because the outage class *is* launchd-level.

See ``deadman`` for the emitter and its inert-by-default contract.
"""
