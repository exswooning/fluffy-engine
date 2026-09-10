/**
 * Fluffy Engine — Sales Logger (Google Apps Script)
 *
 * Bind this to the sales Google Sheet (Extensions > Apps Script), run
 * `logSales` once to authorize, then add a time-driven trigger for it.
 * See SETUP.md for the full walkthrough.
 */

var API_URL = 'https://leadeboard.backend.nest.net.np/get_today_invoice_payments';
var FRONTEND_ENCRYPTION_KEY = 'HelloNamasteFromNestNepal';
var SALES_SHEET = 'Sales Data';
var DASHBOARD_SHEET = 'Dashboard';
var HEADERS = ['Timestamp', 'Operator', 'Source', 'Invoice ID', 'Amount', 'Sale Date'];

// --- Pure logic (no Apps Script services — covered by test.js) ---

function invoiceKey(source, invoiceId) {
  return source + ':' + invoiceId;
}

function filterNewInvoices(invoices, existingKeys) {
  return invoices.filter(function (inv) {
    return !existingKeys.has(invoiceKey(inv.source, inv.invoice_id));
  });
}

function invoiceToRow(inv, scrapedAt) {
  return [
    scrapedAt,
    (inv.admin_name || 'Unknown').trim(),
    inv.source || 'unknown',
    String(inv.invoice_id || ''),
    inv.amount || 0,
    inv.date || '',
  ];
}

function round2(n) {
  return Math.round(n * 100) / 100;
}

function computeOperatorTotals(records) {
  // records: [{operator, amount, saleDate}]
  var totals = {};
  records.forEach(function (r) {
    var op = r.operator || 'Unknown';
    if (!totals[op]) totals[op] = { total: 0, count: 0, last: '' };
    totals[op].total += Number(r.amount) || 0;
    totals[op].count += 1;
    var saleDate = String(r.saleDate || '');
    if (saleDate > totals[op].last) totals[op].last = saleDate;
  });
  return totals;
}

function buildDashboardRows(totals) {
  var header = ['Operator', 'Total Sales (Rs)', 'Sale Count', 'Avg Sale (Rs)', 'Last Sale'];
  var body = Object.keys(totals)
    .map(function (op) {
      var d = totals[op];
      var avg = d.count ? d.total / d.count : 0;
      return [op, round2(d.total), d.count, round2(avg), d.last];
    })
    .sort(function (a, b) {
      return b[1] - a[1];
    });
  return [header].concat(body);
}

// --- Apps Script I/O ---

function fetchTodaysInvoices() {
  var res = UrlFetchApp.fetch(API_URL, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ frontendEncryptionKey: FRONTEND_ENCRYPTION_KEY }),
    muteHttpExceptions: true,
  });
  if (res.getResponseCode() !== 200) {
    throw new Error('API error ' + res.getResponseCode() + ': ' + res.getContentText());
  }
  return JSON.parse(res.getContentText());
}

function getOrCreateSheet(ss, name) {
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  return sheet;
}

function updateSalesData(ss, invoices) {
  var sheet = getOrCreateSheet(ss, SALES_SHEET);
  if (sheet.getLastRow() === 0) sheet.appendRow(HEADERS);

  var lastRow = sheet.getLastRow();
  var existingKeys = new Set();
  if (lastRow > 1) {
    var data = sheet.getRange(2, 1, lastRow - 1, HEADERS.length).getValues();
    data.forEach(function (row) {
      existingKeys.add(invoiceKey(row[2], row[3])); // Source, Invoice ID
    });
  }

  var newInvoices = filterNewInvoices(invoices, existingKeys);

  if (newInvoices.length === 0) {
    Logger.log('No new sales.');
    return 0;
  }

  var scrapedAt = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');
  var rows = newInvoices.map(function (inv) {
    return invoiceToRow(inv, scrapedAt);
  });
  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, HEADERS.length).setValues(rows);
  Logger.log('Appended ' + rows.length + ' new sales.');
  return rows.length;
}

function rebuildDashboard(ss) {
  var salesSheet = ss.getSheetByName(SALES_SHEET);
  var lastRow = salesSheet.getLastRow();
  var records = [];

  if (lastRow > 1) {
    var data = salesSheet.getRange(2, 1, lastRow - 1, HEADERS.length).getValues();
    records = data.map(function (row) {
      return { operator: row[1], amount: row[4], saleDate: row[5] };
    });
  }

  var totals = computeOperatorTotals(records);
  var rows = buildDashboardRows(totals);

  var dash = ss.getSheetByName(DASHBOARD_SHEET);
  var isNew = !dash;
  if (isNew) dash = ss.insertSheet(DASHBOARD_SHEET);
  dash.clear();
  dash.getRange(1, 1, rows.length, rows[0].length).setValues(rows);
  Logger.log('Dashboard rebuilt with ' + (rows.length - 1) + ' operators.');

  if (isNew && rows.length > 1) {
    var chart = dash
      .newChart()
      .setChartType(Charts.ChartType.COLUMN)
      .addRange(dash.getRange(1, 1, rows.length, 2))
      .setPosition(1, 7, 0, 0)
      .setOption('title', 'Sales by Operator')
      .setOption('legend', 'none')
      .build();
    dash.insertChart(chart);
  }
}

/** Entry point — wire this to a time-driven trigger. */
function logSales() {
  var invoices = fetchTodaysInvoices();
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  updateSalesData(ss, invoices);
  rebuildDashboard(ss);
}

// Only present under Node (for test.js); Apps Script has no `module` global.
if (typeof module !== 'undefined') {
  module.exports = {
    invoiceKey: invoiceKey,
    filterNewInvoices: filterNewInvoices,
    invoiceToRow: invoiceToRow,
    computeOperatorTotals: computeOperatorTotals,
    buildDashboardRows: buildDashboardRows,
  };
}
