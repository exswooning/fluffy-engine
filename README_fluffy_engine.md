# Fluffy Engine — Sales Logger

Logs every sale from https://leaderboard.nest.net.np by operator into a Google
Sheet, with a live per-operator Dashboard tab (totals, sale count, average
sale, last sale time, bar chart).

## How it works

The leaderboard's own frontend calls a JSON API for its data
(`POST https://leadeboard.backend.nest.net.np/get_today_invoice_payments`),
which already returns each sale's operator (`admin_name`), amount, invoice
ID, and platform (`source`). [apps_script/Code.gs](apps_script/Code.gs) calls
that same API on a schedule and writes the results straight into the Sheet —
no browser automation involved.

- **Sales Data** tab: one row per sale, deduplicated by source + invoice ID
- **Dashboard** tab: rebuilt every run from all rows in Sales Data — total
  sales, sale count, average sale, and last sale time per operator, sorted
  highest-total first, with a chart

## Setup

See [apps_script/SETUP.md](apps_script/SETUP.md) — paste `Code.gs` into the
Sheet's Extensions → Apps Script editor and add a time-driven trigger. No
server, no service-account credentials, no CI.

## Why not GitHub Actions

This used to run as a Selenium scraper on a GitHub Actions cron. Two things
broke it for months without anyone noticing:

1. The target site was rebuilt (now at `leaderboard.nest.net.np`, previously
   `std.nest.net.np`) — the old scraper kept hitting a dead URL.
2. GitHub auto-disables scheduled workflows after 60 days without any repo
   activity, and nothing was set up to alert on failed runs — so it failed
   silently.

Apps Script removes the whole failure class: it's bound directly to the
Sheet (no separate credentials to rotate), Google doesn't disable triggers
for repo inactivity because there's no repo involved, and failure
notifications are one checkbox away.

## Repository layout

```
fluffy-engine/
├── apps_script/
│   ├── Code.gs      # The logger — paste into Apps Script
│   ├── test.js       # node test.js — self-check for dedup/aggregation logic
│   └── SETUP.md      # Step-by-step setup
└── README_fluffy_engine.md
```
