"""framework.watchdog — independent OUTCOME-monitoring watchdog.

Verifies that declared outcomes actually HAPPENED (not just that processes ran),
and routes failures by tier (auto-fix / escalate-to-Chair / drift-note). Built
2026-06-29 after a briefing cron exited clean while its Telegram send silently
400'd for days. See docs/outcome-watchdog.md.
"""
