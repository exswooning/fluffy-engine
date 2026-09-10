# Setup (one-time, ~5 minutes)

1. Open the [Sales Data Sheet](https://docs.google.com/spreadsheets/d/1E7rx09A7fBZCk3MsbxQ1dZgqWyvZFd95hRRpd9v6uSM) → **Extensions → Apps Script**.
2. Delete whatever's in the default `Code.gs` and paste in this folder's `Code.gs`.
3. Save (Ctrl/Cmd+S), then select the `logSales` function and click **Run**. Google will
   ask you to authorize access to the spreadsheet and to make external requests —
   accept it (it's your own script acting on your own sheet).
4. Check the Sheet — it should now have a **Sales Data** tab with today's invoices and a
   **Dashboard** tab with per-operator totals and a chart.
5. In the Apps Script editor, click the clock icon (**Triggers**) → **Add Trigger**:
   - Function: `logSales`
   - Event source: `Time-driven`
   - Type: `Hours timer` → every 1 or 6 hours (your call)
   - Save.
6. Still on the Triggers page, click the three-dot menu on the trigger → **Edit trigger** →
   under failure notification settings choose **Notify me immediately**. This is the piece
   the old GitHub Actions setup was missing — it failed silently for 4 months because
   nothing ever paged anyone.

That's it — no server, no secrets file, no CI to babysit. The script runs as you, against
your own sheet, on Google's infrastructure.

## Updating the script later

Edit `Code.gs` in this repo, then copy-paste the new version into the Apps Script editor
and save. There's no deploy step — saved code takes effect on the next trigger run.

## Local check

`node test.js` runs the dedup/aggregation logic against fixed sample data (no network,
no Google account needed).
