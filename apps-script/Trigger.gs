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
var TAB_GID = 1668779070;   // the Audit Requests tab (the Google Form's tab)

function requestsTab_() {
  var sheets = SpreadsheetApp.getActive().getSheets();
  for (var i = 0; i < sheets.length; i++) if (sheets[i].getSheetId() === TAB_GID) return sheets[i];
  return SpreadsheetApp.getActive().getSheetByName('Audit Requests');
}

function unfinishedRows_(onlyRows) {
  var tab = requestsTab_();
  var values = tab.getDataRange().getDisplayValues();
  if (values.length < 2) return [values[0] || []];
  var head = values[0];
  var col = function (prefix) { for (var i = 0; i < head.length; i++) if (String(head[i]).toLowerCase().indexOf(prefix.toLowerCase()) === 0) return i; return -1; };
  var cStatus = col('Status'), cResults = col('Audit Results'), cUrl = col('Dealer URL'), cGroup = col('Auto Group Name');
  var out = [head];
  for (var r = 1; r < values.length; r++) {
    var row = values[r];
    var rowNumber = r + 1;
    if (onlyRows && onlyRows.indexOf(rowNumber) < 0) {
      // a group's store rows arrive under the submitted row: send every unfinished row that shares its Auto Group Name
      var g = cGroup >= 0 ? String(row[cGroup]).trim() : '';
      var submittedGroup = false;
      for (var k = 0; k < onlyRows.length; k++) { var v = values[onlyRows[k] - 1]; if (v && cGroup >= 0 && g && String(v[cGroup]).trim().toLowerCase() === g.toLowerCase()) submittedGroup = true; }
      if (!submittedGroup) continue;
    }
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
  var url = props.getProperty('COLLECTOR_URL'), secret = props.getProperty('TRIGGER_SECRET');
  if (!url || !secret) { Logger.log('COLLECTOR_URL or TRIGGER_SECRET is not set in Script Properties'); return; }
  if (rows.length < 2) { Logger.log(source + ': nothing unfinished to send'); return; }
  var res = UrlFetchApp.fetch(url, {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { 'X-Trigger-Secret': secret },
    payload: JSON.stringify({ source: source, sent_at: new Date().toISOString(), rows: rows })
  });
  Logger.log(source + ': ' + (rows.length - 1) + ' row(s) sent, collector answered ' + res.getResponseCode() + ' ' + res.getContentText().slice(0, 300));
}

// A consultant's request landed through the form. The Group Requests script adds a group's store rows a moment later,
// so a group goes out with its Store websites list and the collector builds the stores from that.
function onRequestSubmitted(e) {
  var rowNumber = e && e.range ? e.range.getRow() : null;
  Utilities.sleep(5000);   // let Group Requests.gs add the store rows and sort the tab first
  send_(unfinishedRows_(null), 'form submit' + (rowNumber ? ' row ' + rowNumber : ''));
}

// A row added or changed by hand (an audit asked for in chat gets its row first; clearing a Status puts a row back in line)
function onSheetChanged(e) {
  if (e && e.changeType && ['INSERT_ROW', 'EDIT', 'OTHER'].indexOf(e.changeType) < 0) return;
  send_(unfinishedRows_(null), 'sheet change ' + (e && e.changeType ? e.changeType : ''));
}

// Every hour: whatever is still unfinished (a push the VM missed while it was down runs now; rows already run are ignored there)
function sweepUnfinished() {
  send_(unfinishedRows_(null), 'hourly sweep');
}
