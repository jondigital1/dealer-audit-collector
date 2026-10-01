/**
 * Dealer Audit Requests: tell the collector on the agents VM to go to work the moment a request lands.
 *
 * Install (once, in the sheet: Extensions > Apps Script, beside the emailer and Group Requests.gs):
 *   1. Paste this file in as Trigger.gs and save.
 *   2. Project Settings > Script Properties: add COLLECTOR_URL (the Funnel address, for example
 *      https://agents.taild0ebeb.ts.net/trigger) and TRIGGER_SECRET (the same value as TRIGGER_SECRET in the VM's .env).
 *   3. Triggers (the clock icon) > Add Trigger, three times:
 *        onRequestSubmitted  from spreadsheet, On form submit
 *        onSheetChanged      from spreadsheet, On change
 *        sweepUnfinished     time-driven, every hour
 *      (the form submit catches a consultant's request, the change catches a row added or cleared by hand, and the
 *      hourly sweep catches anything a missed push left behind; the collector runs a row once whatever sends it.)
 *   4. Run sweepUnfinished once from the editor to authorize the script and check the log for "202".
 *
 * It only reads the Audit Requests tab and sends rows whose Status and Audit Results are blank. It writes nothing.
 */
var TRIGGER_TAB_GID = 1668779070;

function requestsTab_() {
  var sheets = SpreadsheetApp.getActive().getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() === TRIGGER_TAB_GID) return sheets[i];
  }
  return SpreadsheetApp.getActive().getSheetByName('Audit Requests');
}

function colIndex_(head, prefix) {
  var p = prefix.toLowerCase();
  for (var i = 0; i < head.length; i++) {
    if (String(head[i]).toLowerCase().indexOf(p) === 0) return i;
  }
  return -1;
}

// The tab's header row plus every row whose Status and Audit Results are blank (the rows still waiting on an audit)
function unfinishedRows_() {
  var tab = requestsTab_();
  var values = tab.getDataRange().getDisplayValues();
  if (values.length < 2) return [values[0] || []];
  var head = values[0];
  var cStatus = colIndex_(head, 'Status');
  var cResults = colIndex_(head, 'Audit Results');
  var cUrl = colIndex_(head, 'Dealer URL');
  var out = [head];
  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    var status = cStatus >= 0 ? String(row[cStatus]).trim() : '';
    var results = cResults >= 0 ? String(row[cResults]).trim() : '';
    var url = cUrl >= 0 ? String(row[cUrl]).trim() : '';
    if (status || results || !url) continue;
    out.push(row);
  }
  return out;
}

function send_(rows, source) {
  var props = PropertiesService.getScriptProperties();
  var url = props.getProperty('COLLECTOR_URL');
  var secret = props.getProperty('TRIGGER_SECRET');
  if (!url || !secret) {
    Logger.log('COLLECTOR_URL or TRIGGER_SECRET is not set');
    return;
  }
  if (rows.length < 2) {
    Logger.log(source + ': nothing unfinished to send');
    return;
  }
  var body = {
    source: source,
    sent_at: new Date().toISOString(),
    rows: rows
  };
  var res = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    headers: { 'X-Trigger-Secret': secret },
    payload: JSON.stringify(body)
  });
  Logger.log(source + ': ' + (rows.length - 1) + ' row(s) sent');
  Logger.log('collector answered ' + res.getResponseCode());
  Logger.log(res.getContentText().slice(0, 300));
}

// A consultant's request landed through the form; the Group Requests script adds a group's store rows a moment later
function onRequestSubmitted(e) {
  Utilities.sleep(5000);
  send_(unfinishedRows_(), 'form submit');
}

// A row added or changed by hand (an audit asked for in chat gets its row first; clearing a Status puts a row back)
function onSheetChanged(e) {
  var kind = e && e.changeType ? e.changeType : '';
  if (kind && ['INSERT_ROW', 'EDIT', 'OTHER'].indexOf(kind) < 0) return;
  send_(unfinishedRows_(), 'sheet change ' + kind);
}

// Every hour: whatever is still unfinished (the collector ignores rows it already ran)
function sweepUnfinished() {
  send_(unfinishedRows_(), 'hourly sweep');
}
