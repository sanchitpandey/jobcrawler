"""
review_server.py
Local Flask web server for reviewing scored jobs and approving a batch.

  1. Run: python review_server.py
  2. Open: http://localhost:5055
  3. Review the table, tick the jobs you want to apply to
  4. Click "Approve Selected"” those jobs are marked 'approved' in the DB
  5. Run: python apply.py

Filters:
  - Shows only jobs with status='new' and fit_score >= MIN_REVIEW_SCORE (default 60)
  - Status tabs: All / Strong Apply / Apply / Borderline / Manual Review
"""

from __future__ import annotations
import sqlite3
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from config import DB_PATH, MIN_REVIEW_SCORE, REVIEW_SERVER_PORT

app = Flask(__name__)

def get_jobs_for_review(verdict_filter: str = "all") -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    base = """
        SELECT id, company, title, location, url,
               fit_score, comp_est, verdict, gaps
        FROM   jobs
        WHERE  fit_score >= ? AND status IN ('new', 'manual_review')
    """
    params = [MIN_REVIEW_SCORE]
    if verdict_filter != "all":
        base += " AND verdict = ?"
        params.append(verdict_filter)
    base += " ORDER BY fit_score DESC LIMIT 200"
    rows = conn.execute(base, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def approve_jobs(job_ids: list[str]):
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join("?" * len(job_ids))
    conn.execute(
        f"UPDATE jobs SET status='approved' WHERE id IN ({placeholders})",
        job_ids
    )
    conn.commit()
    conn.close()


def skip_jobs(job_ids: list[str]):
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join("?" * len(job_ids))
    conn.execute(
        f"UPDATE jobs SET status='skipped' WHERE id IN ({placeholders})",
        job_ids
    )
    conn.commit()
    conn.close()


def get_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    stats = {}
    for status in ["new", "approved", "applied", "manual_review", "skipped", "error", "interview", "rejected"]:
        stats[status] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status=?", (status,)
        ).fetchone()[0]
    conn.close()
    return stats


HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Review Dashboard</title>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d27; --border: #2d3142;
    --text: #e8eaf0; --muted: #6b7280; --accent: #6366f1;
    --green: #22c55e; --yellow: #f59e0b; --red: #ef4444; --blue: #3b82f6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Inter', system-ui, sans-serif;
         font-size: 14px; line-height: 1.5; }
  .header { padding: 20px 32px; border-bottom: 1px solid var(--border);
            display: flex; align-items: center; justify-content: space-between; }
  .header h1 { font-size: 18px; font-weight: 600; letter-spacing: -0.3px; }
  .stats { display: flex; gap: 20px; flex-wrap: wrap; }
  .stat { display: flex; flex-direction: column; align-items: center; }
  .stat-num { font-size: 22px; font-weight: 700; }
  .stat-lbl { font-size: 11px; color: var(--muted); text-transform: uppercase; }
  .toolbar { padding: 16px 32px; display: flex; gap: 12px; align-items: center;
             border-bottom: 1px solid var(--border); flex-wrap: wrap; }
  .tabs { display: flex; gap: 4px; }
  .tab { padding: 6px 14px; border-radius: 6px; cursor: pointer; border: 1px solid var(--border);
         background: transparent; color: var(--muted); font-size: 13px; transition: all .15s; }
  .tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .tab:hover:not(.active) { border-color: var(--accent); color: var(--text); }
  .btn { padding: 8px 18px; border-radius: 8px; font-size: 13px; font-weight: 500;
         cursor: pointer; border: none; transition: all .15s; }
  .btn-approve { background: var(--green); color: #000; }
  .btn-approve:hover { background: #16a34a; }
  .btn-skip { background: var(--border); color: var(--muted); }
  .btn-skip:hover { background: #374151; color: var(--text); }
  .btn-selall { background: transparent; border: 1px solid var(--border);
                color: var(--muted); }
  .spacer { flex: 1; }
  .sel-count { color: var(--accent); font-weight: 600; font-size: 13px; min-width: 90px; }
  table { width: 100%; border-collapse: collapse; }
  thead th { padding: 10px 12px; text-align: left; font-size: 11px; font-weight: 600;
             text-transform: uppercase; letter-spacing: .5px; color: var(--muted);
             background: var(--surface); border-bottom: 1px solid var(--border);
             position: sticky; top: 0; z-index: 2; }
  thead th:first-child { width: 36px; }
  tbody tr { border-bottom: 1px solid var(--border); transition: background .1s; cursor: pointer; }
  tbody tr:hover { background: var(--surface); }
  tbody tr.selected { background: rgba(99,102,241,.12); }
  td { padding: 10px 12px; vertical-align: middle; }
  .score { font-weight: 700; font-size: 16px; }
  .score.s80 { color: var(--green); }
  .score.s60 { color: var(--yellow); }
  .score.s40 { color: #fb923c; }
  .score.s0  { color: var(--muted); }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
           font-size: 11px; font-weight: 600; text-transform: uppercase; }
  .badge-strong_apply { background: rgba(34,197,94,.15); color: var(--green); }
  .badge-apply        { background: rgba(59,130,246,.15); color: var(--blue); }
  .badge-borderline   { background: rgba(245,158,11,.15); color: var(--yellow); }
  .badge-skip         { background: rgba(107,114,128,.15); color: var(--muted); }
  .company { font-weight: 600; }
  .title   { color: var(--muted); font-size: 13px; }
  .comp-est { color: var(--green); font-size: 12px; }
  .gaps { font-size: 11px; color: var(--muted); max-width: 220px; }
  .gap-tag { display: inline-block; background: var(--border); border-radius: 4px;
             padding: 1px 6px; margin: 1px 2px 1px 0; }
  a.url-link { color: var(--accent); text-decoration: none; font-size: 12px; }
  a.url-link:hover { text-decoration: underline; }
  .table-wrap { overflow: auto; max-height: calc(100vh - 180px); }
  .toast { position: fixed; bottom: 28px; right: 28px; padding: 12px 22px;
           border-radius: 10px; background: var(--green); color: #000;
           font-weight: 600; font-size: 14px; box-shadow: 0 4px 20px rgba(0,0,0,.4);
           opacity: 0; transform: translateY(10px); transition: all .3s; z-index: 99; }
  .toast.show { opacity: 1; transform: translateY(0); }
  input[type=checkbox] { width: 16px; height: 16px; cursor: pointer;
                         accent-color: var(--accent); }
  .empty { padding: 60px; text-align: center; color: var(--muted); }
</style>
</head>
<body>

<div class="header">
  <h1>âš¡ Job Review Dashboard</h1>
  <div class="stats" id="stats-bar"><!-- filled by JS --></div>
</div>

<div class="toolbar">
  <div class="tabs" id="tabs">
    <button class="tab active" data-filter="all">All</button>
    <button class="tab" data-filter="strong_apply">Strong Apply</button>
    <button class="tab" data-filter="apply">Apply</button>
    <button class="tab" data-filter="borderline">Borderline</button>
  </div>
  <div class="spacer"></div>
  <span class="sel-count" id="sel-count">0 selected</span>
  <button class="btn btn-selall" onclick="toggleSelectAll()">Select All</button>
  <button class="btn btn-skip"   onclick="actionSelected('skip')">Skip Selected</button>
  <button class="btn btn-approve" onclick="actionSelected('approve')">Approve Selected</button>
</div>

<div class="table-wrap">
<table>
  <thead>
    <tr>
      <th><input type="checkbox" id="master-check" onchange="masterToggle(this)"></th>
      <th>Score</th>
      <th>Verdict</th>
      <th>Company</th>
      <th>Title</th>
      <th>Location</th>
      <th>Est. Comp</th>
      <th>Gaps</th>
      <th>Link</th>
    </tr>
  </thead>
  <tbody id="job-table-body">
    <tr><td colspan="9" class="empty">Loadingâ€¦</td></tr>
  </tbody>
</table>
</div>

<div class="toast" id="toast"></div>

<script>
let allJobs = [];
let currentFilter = 'all';

async function loadJobs(filter) {
  currentFilter = filter;
  const res  = await fetch('/api/jobs?filter=' + filter);
  allJobs    = await res.json();
  renderTable(allJobs);
}

async function loadStats() {
  const res  = await fetch('/api/stats');
  const data = await res.json();
  const bar  = document.getElementById('stats-bar');
  const cols = [
    ['new',           data.new,           '#6366f1'],
    ['approved',      data.approved,      '#22c55e'],
    ['applied',       data.applied,       '#3b82f6'],
    ['manual review', data.manual_review, '#f59e0b'],
  ];
  bar.innerHTML = cols.map(([l, n, c]) =>
    `<div class="stat"><span class="stat-num" style="color:${c}">${n}</span>
     <span class="stat-lbl">${l}</span></div>`
  ).join('');
}

function scoreClass(s) {
  if (s >= 80) return 's80';
  if (s >= 60) return 's60';
  if (s >= 40) return 's40';
  return 's0';
}

function renderTable(jobs) {
  const tbody = document.getElementById('job-table-body');
  if (!jobs.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty">No jobs match this filter.</td></tr>';
    return;
  }
  tbody.innerHTML = jobs.map(j => {
    const sc    = Math.round(j.fit_score || 0);
    const gaps  = tryParseGaps(j.gaps);
    const gapsHtml = gaps.slice(0,3).map(g =>
      `<span class="gap-tag">${escHtml(g)}</span>`).join('');
    return `
    <tr data-id="${j.id}" onclick="toggleRow(this)">
      <td><input type="checkbox" class="row-check" value="${j.id}"
          onclick="event.stopPropagation(); updateCount()"></td>
      <td><span class="score ${scoreClass(sc)}">${sc}</span></td>
      <td><span class="badge badge-${j.verdict}">${j.verdict || 'â€”'}</span></td>
      <td><div class="company">${escHtml(j.company || '')}</div></td>
      <td><div class="title">${escHtml(j.title || '')}</div></td>
      <td>${escHtml(j.location || '')}</td>
      <td><div class="comp-est">${escHtml(j.comp_est || '?')}</div></td>
      <td><div class="gaps">${gapsHtml}</div></td>
      <td><a class="url-link" href="${escHtml(j.url||'')}" target="_blank"
          onclick="event.stopPropagation()">Open â†—</a></td>
    </tr>`;
  }).join('');
  updateCount();
}

function tryParseGaps(raw) {
  if (!raw) return [];
  try { return JSON.parse(raw); }
  catch { return raw.split('|').map(s => s.trim()).filter(Boolean); }
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toggleRow(tr) {
  const cb = tr.querySelector('.row-check');
  cb.checked = !cb.checked;
  tr.classList.toggle('selected', cb.checked);
  updateCount();
}

function updateCount() {
  const n = document.querySelectorAll('.row-check:checked').length;
  document.getElementById('sel-count').textContent = n + ' selected';
}

function masterToggle(master) {
  document.querySelectorAll('.row-check').forEach(cb => {
    cb.checked = master.checked;
    cb.closest('tr').classList.toggle('selected', master.checked);
  });
  updateCount();
}

function toggleSelectAll() {
  const boxes = document.querySelectorAll('.row-check');
  const anyUnchecked = [...boxes].some(cb => !cb.checked);
  boxes.forEach(cb => {
    cb.checked = anyUnchecked;
    cb.closest('tr').classList.toggle('selected', anyUnchecked);
  });
  updateCount();
}

function getSelectedIds() {
  return [...document.querySelectorAll('.row-check:checked')].map(cb => cb.value);
}

async function actionSelected(action) {
  const ids = getSelectedIds();
  if (!ids.length) { showToast('Nothing selected', '#f59e0b'); return; }

  const res = await fetch('/api/' + action, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ids})
  });
  const data = await res.json();

  if (action === 'approve') {
    showToast(`${ids.length} job(s) approved run python apply.py`, '#22c55e');
  } else {
    showToast(`Skipped ${ids.length} job(s)`, '#6b7280');
  }
  await loadStats();
  await loadJobs(currentFilter);
}

function showToast(msg, color = '#22c55e') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.background = color;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3500);
}

// Tab switching
document.getElementById('tabs').addEventListener('click', e => {
  const tab = e.target.closest('.tab');
  if (!tab) return;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  loadJobs(tab.dataset.filter);
});

// Init
loadStats();
loadJobs('all');
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/jobs")
def api_jobs():
    verdict_filter = request.args.get("filter", "all")
    jobs = get_jobs_for_review(verdict_filter)
    return jsonify(jobs)


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/api/approve", methods=["POST"])
def api_approve():
    data = request.get_json()
    ids  = data.get("ids", [])
    if ids:
        approve_jobs(ids)
    return jsonify({"approved": len(ids)})


@app.route("/api/skip", methods=["POST"])
def api_skip():
    data = request.get_json()
    ids  = data.get("ids", [])
    if ids:
        skip_jobs(ids)
    return jsonify({"skipped": len(ids)})


if __name__ == "__main__":
    print("\n  Job Review Server")
    print(f"  Open: http://localhost:{REVIEW_SERVER_PORT}")
    print("  After approving, run: python apply.py")
    print("  Press Ctrl+C to stop.\n")
    app.run(host="127.0.0.1", port=REVIEW_SERVER_PORT, debug=False)
