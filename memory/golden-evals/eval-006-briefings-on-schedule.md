# Eval: Daily Briefings Delivered On Schedule

Category: communication
Tests: CoS produces briefings at the configured `briefing_times` slots (instance/config/platform.yml; fleet default 07:30 and 19:30 Captain-local)

## Scenario
Watchdog cron triggers briefing at scheduled time. CoS receives the trigger via Redis.

## Expected Behavior
1. Launchd fires at the platform.yml `briefing_times` slots (fleet default 07:30/19:30 Captain-local, DST-aware)
2. Redis trigger delivered to CoS via post-tool-use hook
3. CoS compiles status from all Officers
4. Briefing posted to Warroom group
5. Briefing published to Notion Daily Briefings DB

## Failure Condition
- Briefing trigger not delivered (cron or Redis failure)
- CoS ignores the trigger
- Briefing posted more than 30 minutes late
- Briefing missing status from any active Officer
