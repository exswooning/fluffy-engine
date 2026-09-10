// Self-check for the dedup/aggregation logic in Code.gs. Run: node test.js
const assert = require('assert');
const { invoiceKey, filterNewInvoices, invoiceToRow, computeOperatorTotals, buildDashboardRows } = require('./Code.gs');

const invoices = [
  { admin_name: 'Aryan Pal', source: 'nest', invoice_id: '1', amount: 100, date: '2026-09-10T01:00:00Z' },
  { admin_name: 'Sahaj Maharjan', source: 'nest', invoice_id: '2', amount: 50, date: '2026-09-10T02:00:00Z' },
  { admin_name: 'Sahaj Maharjan', source: 'sms', invoice_id: '1', amount: 25, date: '2026-09-10T03:00:00Z' },
];

// Same invoice_id "1" under different sources must both survive; an exact
// source+invoice_id match already logged must be dropped.
const existing = new Set([invoiceKey('nest', '1')]);
const fresh = filterNewInvoices(invoices, existing);
assert.deepStrictEqual(
  fresh.map((inv) => invoiceKey(inv.source, inv.invoice_id)).sort(),
  ['nest:2', 'sms:1']
);

const row = invoiceToRow(invoices[0], '2026-09-10 12:00:00');
assert.deepStrictEqual(row, ['2026-09-10 12:00:00', 'Aryan Pal', 'nest', '1', 100, '2026-09-10T01:00:00Z']);

const totals = computeOperatorTotals([
  { operator: 'Aryan Pal', amount: '100', saleDate: '2026-09-10T01:00:00Z' },
  { operator: 'Sahaj Maharjan', amount: '50', saleDate: '2026-09-10T02:00:00Z' },
  { operator: 'Sahaj Maharjan', amount: '25', saleDate: '2026-09-10T03:00:00Z' },
]);
assert.strictEqual(totals['Sahaj Maharjan'].total, 75);
assert.strictEqual(totals['Sahaj Maharjan'].count, 2);
assert.strictEqual(totals['Sahaj Maharjan'].last, '2026-09-10T03:00:00Z');

const dash = buildDashboardRows(totals);
assert.deepStrictEqual(dash[0], ['Operator', 'Total Sales (Rs)', 'Sale Count', 'Avg Sale (Rs)', 'Last Sale']);
assert.strictEqual(dash[1][0], 'Aryan Pal'); // total 100 > Sahaj's combined 75, sorts first

console.log('OK');
