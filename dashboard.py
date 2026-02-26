"""
BioVault Agent — Live Dashboard
---------------------------------
GET /dashboard — single-page, fully live dashboard.

Layout: two-column.
  Left sidebar  — upload, simulate, agent KPIs, scrollable document list
  Right panel   — document detail: image preview, extraction summary,
                  FHIR R4 JSON viewer, safety validation checks

All data refreshes every 8 seconds via JS fetch — zero page reloads.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

import database as db

logger = logging.getLogger("biovault.dashboard")


router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Live two-panel agent dashboard."""
    # Server-side seed only — JS takes over immediately after load
    heartbeat = db.get_heartbeat() or {}
    stats = db.get_stats()
    started_at = heartbeat.get("started_at", "")
    uptime_str = _format_uptime(started_at)
    last_seen = heartbeat.get("last_seen", "")
    agent_status = "RUNNING" if _is_recent(last_seen, 90) else "STALLED"
    status_color = "#22c55e" if agent_status == "RUNNING" else "#ef4444"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>BioVault Agent</title>
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    :root{{
      --bg:#0a0f1e;--panel:#0f172a;--panel2:#080d1a;--border:#1e293b;
      --accent:#00d4aa;--warn:#f59e0b;--err:#ef4444;--blue:#3b82f6;
      --purple:#8b5cf6;--text:#e2e8f0;--muted:#94a3b8;--dim:#475569;
    }}
    html,body{{height:100%;overflow:hidden;background:var(--bg);color:var(--text);
      font-family:'Inter','Segoe UI',system-ui,sans-serif;font-size:14px}}

    /* ── Layout ── */
    .app{{display:flex;height:100vh;overflow:hidden}}
    .sidebar{{width:320px;min-width:200px;max-width:600px;display:flex;flex-direction:column;
      background:var(--panel);overflow:hidden;flex-shrink:0;position:relative}}
    .resize-handle{{
      width:5px;flex-shrink:0;cursor:col-resize;background:transparent;
      border-left:1px solid var(--border);border-right:none;
      transition:background .15s;position:relative;z-index:10;
    }}
    .resize-handle:hover,.resize-handle.dragging{{
      background:var(--blue);border-color:var(--blue);
    }}
    .resize-handle::after{{
      content:'';position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
      width:3px;height:32px;border-radius:3px;
      background:var(--border);transition:background .15s;
    }}
    .resize-handle:hover::after,.resize-handle.dragging::after{{background:var(--blue)}}
    .main{{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}}

    /* ── Header ── */
    .hdr{{display:flex;align-items:center;justify-content:space-between;
      padding:16px 20px;border-bottom:1px solid var(--border);shrink:0}}
    .logo{{display:flex;align-items:center;gap:10px}}
    .logo-icon{{width:36px;height:36px;border-radius:9px;
      background:linear-gradient(135deg,var(--blue),var(--purple));
      display:flex;align-items:center;justify-content:center;font-size:18px}}
    .logo h1{{font-size:17px;font-weight:700;letter-spacing:-.3px}}
    .logo p{{font-size:11px;color:var(--muted);margin-top:1px}}
    .badge{{display:flex;align-items:center;gap:7px;
      background:var(--bg);border:1px solid var(--border);
      border-radius:8px;padding:7px 12px}}
    .pulse{{width:9px;height:9px;border-radius:50%;background:{status_color};
      box-shadow:0 0 0 0 {status_color}55;animation:pulse 2s infinite}}
    @keyframes pulse{{0%{{box-shadow:0 0 0 0 {status_color}55}}
      70%{{box-shadow:0 0 0 7px transparent}}100%{{box-shadow:0 0 0 0 transparent}}}}
    .badge-status{{font-size:12px;font-weight:700;color:{status_color}}}
    .badge-hb{{font-size:10px;color:var(--dim);margin-top:1px}}

    /* ── Sidebar scrollable body ── */
    .sidebar-body{{flex:1;overflow-y:auto;padding:16px}}
    .sidebar-body::-webkit-scrollbar{{width:4px}}
    .sidebar-body::-webkit-scrollbar-track{{background:transparent}}
    .sidebar-body::-webkit-scrollbar-thumb{{background:var(--border);border-radius:4px}}

    /* ── Section label ── */
    .sec-label{{font-size:10px;font-weight:700;text-transform:uppercase;
      letter-spacing:.8px;color:var(--dim);margin-bottom:10px;margin-top:20px}}
    .sec-label:first-child{{margin-top:0}}

    /* ── KPI row ── */
    .kpi-row{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:4px}}
    .kpi{{background:var(--bg);border:1px solid var(--border);border-radius:10px;
      padding:12px 14px}}
    .kpi-val{{font-size:26px;font-weight:800;letter-spacing:-1px;line-height:1}}
    .kpi-lbl{{font-size:10px;color:var(--muted);margin-top:4px;text-transform:uppercase;letter-spacing:.5px}}
    .kpi-sub{{font-size:10px;color:var(--dim);margin-top:2px}}
    .c-green{{color:#22c55e}}.c-red{{color:var(--err)}}.c-blue{{color:var(--blue)}}
    .c-yellow{{color:var(--warn)}}.c-accent{{color:var(--accent)}}.c-muted{{color:var(--muted)}}

    /* ── Queue bar ── */
    .q-bar{{display:flex;gap:12px;flex-wrap:wrap;background:var(--bg);
      border:1px solid var(--border);border-radius:10px;padding:10px 14px;
      font-size:12px;margin-bottom:4px}}
    .q-dot{{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:5px}}

    /* ── Upload zone ── */
    .drop-zone{{border:2px dashed var(--border);border-radius:10px;
      background:var(--bg);padding:20px 16px;text-align:center;cursor:pointer;
      transition:border-color .2s,background .2s;position:relative;margin-bottom:8px}}
    .drop-zone.over{{border-color:var(--accent);background:#00d4aa08}}
    .drop-zone input[type=file]{{position:absolute;inset:0;opacity:0;
      cursor:pointer;width:100%;height:100%}}
    .drop-icon{{font-size:24px;margin-bottom:6px}}
    .drop-text{{font-size:12px;color:var(--muted)}}
    .drop-text strong{{color:var(--text)}}
    .drop-hint{{font-size:10px;color:var(--dim);margin-top:3px}}

    .sim-btn{{width:100%;background:var(--bg);border:1px solid var(--border);
      border-radius:10px;padding:10px;cursor:pointer;color:var(--purple);
      font-size:12px;font-weight:600;transition:border-color .2s,background .2s;
      display:flex;align-items:center;justify-content:center;gap:7px}}
    .sim-btn:hover{{border-color:var(--purple);background:#1a104022}}
    .sim-btn:disabled{{opacity:.5;cursor:not-allowed}}

    .upload-status{{font-size:12px;min-height:18px;margin-top:6px;text-align:center}}
    .us-ok{{color:var(--accent)}}.us-err{{color:var(--err)}}.us-loading{{color:var(--blue)}}

    /* ── Document list ── */
    .doc-item{{display:flex;align-items:center;gap:10px;padding:9px 10px;
      border-radius:8px;cursor:pointer;transition:background .15s;
      border:1px solid transparent;margin-bottom:4px}}
    .doc-item:hover{{background:#ffffff08}}
    .doc-item.active{{background:var(--border);border-color:#334155}}
    .doc-thumb{{width:38px;height:38px;border-radius:6px;object-fit:cover;
      border:1px solid var(--border);background:var(--border);flex-shrink:0}}
    .doc-thumb-ph{{width:38px;height:38px;border-radius:6px;
      background:var(--border);flex-shrink:0;display:flex;align-items:center;
      justify-content:center;font-size:16px;color:var(--dim)}}
    .doc-info{{flex:1;min-width:0}}
    .doc-name{{font-size:12px;font-weight:500;white-space:nowrap;
      overflow:hidden;text-overflow:ellipsis;color:var(--text)}}
    .doc-meta{{font-size:10px;color:var(--muted);margin-top:2px}}
    .status-pill{{display:inline-block;padding:2px 8px;border-radius:20px;
      font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.3px}}

    /* ── Alerts compact ── */
    .alert-item{{background:var(--bg);border:1px solid #ef444440;
      border-left:3px solid var(--err);border-radius:8px;
      padding:8px 10px;margin-bottom:6px;font-size:11px}}
    .alert-sev{{font-weight:700;color:var(--err);margin-bottom:2px;font-size:10px;
      text-transform:uppercase;letter-spacing:.4px}}
    .alert-det{{color:var(--muted);line-height:1.4}}

    /* ── Main right panel ── */
    .main-hdr{{display:flex;align-items:center;justify-content:space-between;
      padding:14px 20px;border-bottom:1px solid var(--border);flex-shrink:0}}
    .main-hdr-title{{font-size:14px;font-weight:600;color:var(--text)}}
    .main-hdr-sub{{font-size:11px;color:var(--muted);margin-top:1px}}

    /* ── Empty state ── */
    .empty-state{{flex:1;display:flex;flex-direction:column;
      align-items:center;justify-content:center;color:var(--dim)}}
    .empty-icon{{font-size:48px;opacity:.2;margin-bottom:16px}}
    .empty-text{{font-size:13px;margin-bottom:6px}}
    .empty-sub{{font-size:11px;color:var(--border)}}

    /* ── Detail layout ── */
    .detail{{flex:1;display:flex;flex-direction:column;overflow:hidden}}
    .detail-top{{display:flex;border-bottom:1px solid var(--border);
      height:260px;flex-shrink:0}}
    .detail-bottom{{display:flex;flex:1;min-height:0}}

    .img-panel{{width:260px;flex-shrink:0;border-right:1px solid var(--border);
      overflow:hidden;background:var(--panel2);position:relative}}
    .img-panel img{{width:100%;height:100%;object-fit:contain;padding:8px}}

    .summary-panel{{flex:1;padding:16px 18px;overflow-y:auto;background:var(--panel2)}}
    .summary-panel::-webkit-scrollbar{{width:4px}}
    .summary-panel::-webkit-scrollbar-thumb{{background:var(--border);border-radius:4px}}

    .summ-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}}
    .summ-card{{background:var(--bg);border:1px solid var(--border);
      border-radius:8px;padding:10px 12px}}
    .summ-card-label{{font-size:10px;text-transform:uppercase;letter-spacing:.6px;
      color:var(--dim);margin-bottom:4px}}
    .summ-card-val{{font-size:13px;font-weight:600;color:var(--text);
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}

    .flag-list{{margin-top:10px}}
    .flag-tag{{display:inline-block;background:#f59e0b18;border:1px solid #f59e0b40;
      color:var(--warn);border-radius:5px;padding:2px 8px;font-size:10px;
      margin:2px 3px 2px 0}}

    .fhir-panel{{flex:1;display:flex;flex-direction:column;
      border-right:1px solid var(--border);min-width:0}}
    .panel-hdr{{display:flex;align-items:center;justify-content:space-between;
      padding:10px 16px;border-bottom:1px solid var(--border);flex-shrink:0;
      background:var(--panel)}}
    .panel-hdr-title{{font-size:12px;font-weight:600;color:var(--text);
      display:flex;align-items:center;gap:6px}}
    .copy-btn{{font-size:10px;padding:3px 9px;border-radius:5px;cursor:pointer;
      color:var(--accent);border:1px solid var(--accent)40;background:transparent;
      transition:background .15s}}
    .copy-btn:hover{{background:var(--accent)18}}
    .json-view{{flex:1;overflow-y:auto;padding:12px 14px;
      background:var(--panel2);font-family:'Fira Code','Courier New',monospace;
      font-size:11px;line-height:1.65;white-space:pre}}
    .json-view::-webkit-scrollbar{{width:4px}}
    .json-view::-webkit-scrollbar-thumb{{background:var(--border);border-radius:4px}}

    /* JSON syntax colours */
    .jk{{color:#7dd3fc}}.js{{color:#86efac}}.jn{{color:#fca5a5}}
    .jb{{color:#c4b5fd}}.jnull{{color:#64748b}}.jicd{{color:var(--accent);font-weight:700}}
    .jdose{{color:#fbbf24}}.jdose-bad{{color:var(--err);font-weight:700;
      text-decoration:underline wavy var(--err)}}

    .valid-panel{{width:320px;flex-shrink:0;display:flex;flex-direction:column;min-width:0}}
    .valid-body{{flex:1;overflow-y:auto;padding:10px 14px;background:var(--panel2)}}
    .valid-body::-webkit-scrollbar{{width:4px}}
    .valid-body::-webkit-scrollbar-thumb{{background:var(--border);border-radius:4px}}

    .check-row{{display:flex;align-items:flex-start;gap:10px;padding:10px 12px;
      border-radius:8px;margin-bottom:6px}}
    .check-row.ok{{background:#00d4aa08;border-left:2px solid var(--accent)}}
    .check-row.fail{{background:#ef444408;border-left:2px solid var(--err)}}
    .check-name{{font-size:12px;font-weight:600}}
    .check-det{{font-size:11px;color:var(--muted);margin-top:3px;line-height:1.4}}

    .dose-alert{{background:#ef444412;border:1px solid #ef444440;
      border-radius:8px;padding:12px 14px;margin-bottom:10px}}
    .dose-alert-title{{font-size:12px;font-weight:700;color:var(--err);margin-bottom:4px}}
    .dose-alert-body{{font-size:11px;color:var(--muted);line-height:1.5}}

    /* ── Footer ── */
    .footer{{flex-shrink:0;padding:6px 20px;border-top:1px solid var(--border);
      font-size:10px;color:var(--dim);display:flex;align-items:center;
      justify-content:space-between}}
    .footer a{{color:var(--blue);text-decoration:none}}
    .footer a:hover{{text-decoration:underline}}

    /* ── Activity feed ── */
    .activity-panel{{
      flex-shrink:0;border-bottom:1px solid var(--border);
      display:flex;flex-direction:column;
      height:200px;background:var(--panel);
    }}
    .activity-scroll{{
      flex:1;overflow-y:auto;padding:6px 0;
    }}
    .activity-scroll::-webkit-scrollbar{{width:4px}}
    .activity-scroll::-webkit-scrollbar-thumb{{background:var(--border);border-radius:4px}}
    .act-row{{
      display:flex;align-items:baseline;gap:8px;
      padding:3px 16px;font-size:11.5px;line-height:1.5;
      border-left:2px solid transparent;
      transition:background .1s;
    }}
    .act-row:hover{{background:#ffffff05}}
    .act-row.level-success{{border-left-color:var(--accent)}}
    .act-row.level-warn{{border-left-color:var(--warn)}}
    .act-row.level-error{{border-left-color:var(--err)}}
    .act-row.level-info{{border-left-color:transparent}}
    .act-ts{{color:var(--dim);font-size:10px;font-family:monospace;flex-shrink:0;width:62px}}
    .act-msg{{color:var(--text);flex:1}}
    .act-stage{{font-size:10px;color:var(--dim);flex-shrink:0;font-family:monospace}}
    .act-active{{
      display:flex;align-items:center;gap:6px;
      padding:2px 16px 6px;font-size:11px;color:var(--accent);
    }}
    .act-spinner{{
      display:inline-block;width:8px;height:8px;border-radius:50%;
      border:2px solid var(--accent)44;border-top-color:var(--accent);
      animation:spin .7s linear infinite;flex-shrink:0
    }}
    @keyframes spin{{to{{transform:rotate(360deg)}}}}
    .act-empty{{
      display:flex;align-items:center;justify-content:center;
      height:100%;font-size:12px;color:var(--dim)
    }}

  </style>
</head>
<body>
<div class="app">

<!-- ══════════════════ LEFT SIDEBAR ══════════════════ -->
<div class="sidebar">

  <!-- Sidebar header -->
  <div class="hdr">
    <div class="logo">
      <div class="logo-icon">🧬</div>
      <div>
        <h1>BioVault Agent</h1>
        <p>Clinical Document Watchdog</p>
      </div>
    </div>
    <div class="badge">
      <div class="pulse" id="pulse-dot"></div>
      <div>
        <div class="badge-status" id="agent-status">{agent_status}</div>
        <div class="badge-hb" id="hb-ts">♥ —</div>
      </div>
    </div>
  </div>

  <div class="sidebar-body">

    <!-- Upload -->
    <div class="sec-label">Upload Document</div>
    <div class="drop-zone" id="drop-zone">
      <input type="file" id="file-input"
        accept="image/jpeg,image/png,image/webp,image/gif,application/pdf" multiple/>
      <div class="drop-icon">📄</div>
      <div class="drop-text"><strong>Click to upload</strong> or drag &amp; drop</div>
      <div class="drop-hint">JPEG · PNG · WebP · PDF &nbsp;|&nbsp; max 20 MB</div>
    </div>
    <button class="sim-btn" id="sim-btn" onclick="runSimulate()">
      ⚗️ Inject Test Batch (5 docs)
    </button>
    <div class="upload-status" id="upload-status"></div>

    <!-- KPIs -->
    <div class="sec-label">Agent Status</div>
    <div class="kpi-row">
      <div class="kpi">
        <div class="kpi-val c-green" id="kpi-processed">—</div>
        <div class="kpi-lbl">Processed</div>
      </div>
      <div class="kpi">
        <div class="kpi-val c-red" id="kpi-flags">—</div>
        <div class="kpi-lbl">Flags Raised</div>
      </div>
      <div class="kpi">
        <div class="kpi-val c-blue" id="kpi-uptime">{uptime_str}</div>
        <div class="kpi-lbl">Uptime</div>
        <div class="kpi-sub" id="kpi-uptime-sub">since start</div>
      </div>
      <div class="kpi">
        <div class="kpi-val c-yellow" id="kpi-pending">—</div>
        <div class="kpi-lbl">Pending</div>
      </div>
    </div>

    <!-- Queue bar -->
    <div class="q-bar" id="q-bar">
      <span><span class="q-dot" style="background:#6b7280"></span><span id="q-pending">0</span> pending</span>
      <span><span class="q-dot" style="background:#3b82f6"></span><span id="q-proc">0</span> processing</span>
      <span><span class="q-dot" style="background:#22c55e"></span><span id="q-done">0</span> complete</span>
      <span><span class="q-dot" style="background:#ef4444"></span><span id="q-fail">0</span> failed</span>
    </div>

    <!-- Alerts -->
    <div id="alerts-section"></div>

    <!-- Document list -->
    <div class="sec-label">Documents</div>
    <div id="doc-list">
      <div style="color:var(--dim);font-size:12px;text-align:center;padding:20px 0">
        No documents yet — upload one or inject a test batch
      </div>
    </div>

  </div><!-- /sidebar-body -->
</div><!-- /sidebar -->

<div class="resize-handle" id="resize-handle" title="Drag to resize"></div>

<!-- ══════════════════ MAIN PANEL ══════════════════ -->
<div class="main">
  <div class="main-hdr">
    <div>
      <div class="main-hdr-title" id="detail-title">Select a document to inspect</div>
      <div class="main-hdr-sub" id="detail-sub">Upload or inject test documents using the sidebar</div>
    </div>
    <div id="detail-badge"></div>
  </div>

  <!-- Live Activity Feed -->
  <div class="activity-panel">
    <div class="panel-hdr">
      <div class="panel-hdr-title">⚡ Agent Activity</div>
      <div id="act-status" style="font-size:11px;color:var(--muted)">0 events</div>
    </div>
    <div id="act-active-bar" style="display:none" class="act-active">
      <span class="act-spinner"></span>
      <span id="act-active-msg">Processing…</span>
    </div>
    <div class="activity-scroll" id="act-scroll">
      <div class="act-empty">Waiting for agent activity…</div>
    </div>
  </div>

  <!-- Empty state -->
  <div class="empty-state" id="empty-state">
    <div class="empty-icon">📋</div>
    <div class="empty-text">No document selected</div>
    <div class="empty-sub">Upload a document or inject a test batch, then click it in the sidebar</div>
  </div>


  <!-- Detail view (hidden until a doc is selected) -->
  <div class="detail" id="detail-view" style="display:none">

    <!-- Top: image + summary -->
    <div class="detail-top">
      <div class="img-panel">
        <img id="doc-img" src="" alt="Document image"
          onerror="this.style.display='none';document.getElementById('img-ph').style.display='flex'"/>
        <div id="img-ph" style="display:none;width:100%;height:100%;
          align-items:center;justify-content:center;color:var(--dim);font-size:32px">📄</div>
      </div>
      <div class="summary-panel" id="summary-panel">
        <div style="color:var(--dim);font-size:12px">Loading…</div>
      </div>
    </div>

    <!-- Bottom: FHIR JSON + Validation -->
    <div class="detail-bottom">

      <div class="fhir-panel">
        <div class="panel-hdr">
          <div class="panel-hdr-title">📋 FHIR R4 Bundle</div>
          <button class="copy-btn" onclick="copyFhir()">Copy JSON</button>
        </div>
        <div class="json-view" id="fhir-json">
          <span style="color:var(--dim)">Processing…</span>
        </div>
      </div>

      <div class="valid-panel">
        <div class="panel-hdr">
          <div class="panel-hdr-title">🛡️ Safety Validation</div>
          <div id="valid-badge" style="font-size:11px;color:var(--muted)"></div>
        </div>
        <div class="valid-body" id="valid-body">
          <div style="color:var(--dim);font-size:12px">Processing…</div>
        </div>
      </div>

    </div>
  </div><!-- /detail-view -->

  <div class="footer">
    <span id="footer-ts">⟳ refreshes every 8s</span>
    <span>
      <a href="/docs">API Docs</a> &nbsp;·&nbsp;
      <a href="/alerts">Alerts JSON</a> &nbsp;·&nbsp;
      <a href="/health">Health</a>
    </span>
  </div>
</div><!-- /main -->
</div><!-- /app -->

<script>
let _selectedDocId = null;
let _fhirData = null;
let _docs = [];
let _startedAt = null;

// ── Sidebar resize ───────────────────────────────────────────────────────────
(function() {{
  const handle  = document.getElementById('resize-handle');
  const sidebar = document.querySelector('.sidebar');
  const MIN_W = 200, MAX_W = 620;
  const STORAGE_KEY = 'bv_sidebar_w';

  // Restore saved width
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) sidebar.style.width = saved + 'px';

  let dragging = false, startX = 0, startW = 0;

  handle.addEventListener('mousedown', e => {{
    dragging = true;
    startX = e.clientX;
    startW = sidebar.getBoundingClientRect().width;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  }});

  document.addEventListener('mousemove', e => {{
    if (!dragging) return;
    const delta = e.clientX - startX;
    const newW  = Math.min(MAX_W, Math.max(MIN_W, startW + delta));
    sidebar.style.width = newW + 'px';
  }});

  document.addEventListener('mouseup', () => {{
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    localStorage.setItem(STORAGE_KEY, Math.round(sidebar.getBoundingClientRect().width));
  }});

  // Double-click to reset to default
  handle.addEventListener('dblclick', () => {{
    sidebar.style.width = '320px';
    localStorage.removeItem(STORAGE_KEY);
  }});
}})();

// ── Bootstrap ───────────────────────────────────────────────────────────────
let _fastPollTimer  = null;
let _lastLogId      = 0;
let _lastPollTime   = Date.now();
let _countdownTimer = null;
const POLL_INTERVAL_S = 30;

(async () => {{
  await refreshAll();
  await refreshActivity();
  setInterval(refreshAll, 8000);
  setInterval(refreshUptime, 1000);
  setInterval(maybeFastPoll, 3000);
  setInterval(tickCountdown, 1000);
}})();

async function maybeFastPoll() {{
  await refreshActivity();
  // If something is processing, also refresh the queue/health immediately
  if (document.getElementById('act-active-bar').style.display !== 'none') {{
    const queue = await fetchJ('/intake/queue').catch(() => null);
    if (queue) updateQueue(queue);
    // Reload selected doc results if it just finished
    if (_selectedDocId) {{
      const sel = (_docs || []).find(d => d.id === _selectedDocId);
      if (sel && sel.status === 'complete') loadDocResults(_selectedDocId);
    }}
  }}
}}

// ── Countdown to next autonomous poll ────────────────────────────────────────
function tickCountdown() {{
  if (!_selectedDocId) return;
  const sel = (_docs || []).find(d => d.id === _selectedDocId);
  if (!sel || sel.status !== 'pending') return;

  const elapsed = Math.floor((Date.now() - _lastPollTime) / 1000);
  const remaining = Math.max(0, POLL_INTERVAL_S - elapsed);
  const el = document.getElementById('countdown-val');
  if (el) el.textContent = remaining;
}}

// ── Master refresh ──────────────────────────────────────────────────────────
async function refreshAll() {{
  const [health, queue, alerts] = await Promise.all([
    fetchJ('/health').catch(() => null),
    fetchJ('/intake/queue').catch(() => null),
    fetchJ('/alerts').catch(() => null),
  ]);

  if (health) updateHealth(health);
  if (queue)  updateQueue(queue);
  if (alerts) updateAlerts(alerts);
  _lastPollTime = Date.now();

  // If selected doc changed state, re-render its panel
  if (_selectedDocId) {{
    const sel = (_docs || []).find(d => d.id === _selectedDocId);
    if (sel) {{
      if (sel.status === 'complete') loadDocResults(_selectedDocId);
      else if (sel.status === 'processing') showProcessingState(sel);
      else if (sel.status === 'pending')    showPendingState(sel);
      else if (sel.status === 'failed')     showFailedState(sel);
    }}
  }}
  // Auto-select newest doc if nothing is selected
  if (!_selectedDocId && _docs.length) {{
    selectDoc(_docs[0].id);
  }}
}}

// ── Health / KPIs ───────────────────────────────────────────────────────────
function updateHealth(h) {{
  setText('kpi-processed', h.documents_processed_total ?? 0);
  const flags = h.flags_raised_total ?? 0;
  setText('kpi-flags', flags);
  document.getElementById('kpi-flags').className = 'kpi-val ' + (flags > 0 ? 'c-red' : 'c-muted');

  const running = h.status === 'running';
  setText('agent-status', running ? 'RUNNING' : 'STALLED');
  document.getElementById('agent-status').style.color = running ? '#22c55e' : '#ef4444';
  document.getElementById('pulse-dot').style.background = running ? '#22c55e' : '#ef4444';
  if (h.heartbeat) setText('hb-ts', '♥ ' + fmtTime(h.heartbeat));
  if (h.started_at && !_startedAt) _startedAt = new Date(h.started_at);
}}

// ── Queue stats ──────────────────────────────────────────────────────────────
function updateQueue(q) {{
  const s = q.stats || {{}};
  setText('q-pending', s.pending ?? 0);
  setText('q-proc',    s.processing ?? 0);
  setText('q-done',    s.complete ?? 0);
  setText('q-fail',    s.failed ?? 0);
  setText('kpi-pending', s.pending ?? 0);

  _docs = q.recent_documents || [];
  renderDocList(_docs);
}}

// ── Alerts ──────────────────────────────────────────────────────────────────
function updateAlerts(a) {{
  const alerts = a.alerts || [];
  const sec = document.getElementById('alerts-section');
  if (!alerts.length) {{ sec.innerHTML = ''; return; }}
  sec.innerHTML = `
    <div class="sec-label" style="color:var(--err)">⚠ Active Alerts (${{alerts.length}})</div>
    ${{alerts.slice(0,3).map(f => `
      <div class="alert-item">
        <div class="alert-sev">${{f.severity}} · ${{f.flag_type}}</div>
        <div class="alert-det">${{esc(f.details.slice(0,100))}}${{f.details.length>100?'…':''}}</div>
        <div style="font-size:10px;color:var(--dim);margin-top:3px">${{f.filename}} · ${{fmtTime(f.timestamp)}}</div>
      </div>
    `).join('')}}
    ${{alerts.length > 3 ? `<div style="font-size:11px;color:var(--dim);text-align:center;padding:4px">+${{alerts.length-3}} more — <a href="/alerts" style="color:var(--blue)">view all</a></div>` : ''}}
  `;
}}

// ── Document list ────────────────────────────────────────────────────────────
function renderDocList(docs) {{
  const el = document.getElementById('doc-list');
  if (!docs.length) {{
    el.innerHTML = '<div style="color:var(--dim);font-size:12px;text-align:center;padding:20px 0">No documents yet — upload one or inject a test batch</div>';
    return;
  }}
  el.innerHTML = docs.map(d => {{
    const sc = statusColor(d.status);
    const isActive = d.id === _selectedDocId;
    return `
      <div class="doc-item ${{isActive ? 'active' : ''}}" onclick="selectDoc('${{d.id}}')" id="di-${{d.id}}">
        <img class="doc-thumb" src="/intake/${{d.id}}/image"
          onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"
          style="display:block"/>
        <div class="doc-thumb-ph" style="display:none">📄</div>
        <div class="doc-info">
          <div class="doc-name" title="${{esc(d.filename)}}">${{esc(d.filename)}}</div>
          <div class="doc-meta">
            <span class="status-pill" style="background:${{sc}}20;color:${{sc}};border:1px solid ${{sc}}40">${{d.status}}</span>
            ${{d.critical_flags_count > 0 ? `<span style="color:var(--err);font-weight:700;font-size:10px;margin-left:4px">⚠ ${{d.critical_flags_count}}</span>` : ''}}
          </div>
          <div style="font-size:10px;color:var(--dim);margin-top:2px">${{fmtTime(d.uploaded_at)}}</div>
        </div>
      </div>`;
  }}).join('');
}}

// ── Select + load doc ────────────────────────────────────────────────────────
async function selectDoc(id) {{
  _selectedDocId = id;

  // Highlight in list
  document.querySelectorAll('.doc-item').forEach(el => el.classList.remove('active'));
  const row = document.getElementById('di-' + id);
  if (row) row.classList.add('active');

  const doc = _docs.find(d => d.id === id);
  if (!doc) return;

  // Update header
  setText('detail-title', doc.filename);
  const sc = statusColor(doc.status);
  document.getElementById('detail-badge').innerHTML =
    `<span class="status-pill" style="background:${{sc}}20;color:${{sc}};border:1px solid ${{sc}}40;padding:4px 12px;font-size:12px">${{doc.status}}</span>`;
  document.getElementById('detail-sub').textContent =
    doc.processed_at ? 'Processed ' + fmtTime(doc.processed_at) :
    doc.uploaded_at  ? 'Uploaded '  + fmtTime(doc.uploaded_at)  : '';

  if      (doc.status === 'pending')    showPendingState(doc);
  else if (doc.status === 'processing') showProcessingState(doc);
  else if (doc.status === 'failed')     showFailedState(doc);
  else if (doc.status === 'complete')   loadDocResults(id);
}}

function _showMainPanel(which) {{
  document.getElementById('empty-state').style.display  = which === 'empty'  ? 'flex' : 'none';
  document.getElementById('detail-view').style.display  = which === 'detail' ? 'flex' : 'none';
}}

function _loadDocImage(id) {{
  const img = document.getElementById('doc-img');
  const ph  = document.getElementById('img-ph');
  if (!img) return;
  img.src = '/intake/' + id + '/image?' + Date.now();
  img.style.display = 'block';
  if (ph) ph.style.display = 'none';
}}

function showPendingState(doc) {{
  _showMainPanel('detail');
  _loadDocImage(doc.id);
  document.getElementById('summary-panel').innerHTML = `
    <div style="display:flex;flex-direction:column;gap:12px;padding:4px 0">
      <div style="display:flex;align-items:center;gap:8px;font-size:13px;font-weight:700;color:var(--text)">
        🕐 Queued for processing
      </div>
      <div style="font-size:12px;color:var(--muted);line-height:1.6">
        The autonomous agent will pick this up automatically within 30 seconds.
        <br/>Or process it right now:
      </div>
      <button onclick="processNow()" id="process-now-btn"
        style="background:linear-gradient(135deg,#3b82f6,#8b5cf6);border:none;
        border-radius:10px;padding:12px 20px;color:#fff;font-size:13px;font-weight:700;
        cursor:pointer;text-align:left;display:flex;align-items:center;gap:8px;width:100%">
        ▶&nbsp; Process Now
      </button>
      <div id="countdown-ring"
        style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);
        background:var(--bg);border:1px solid var(--border);border-radius:20px;padding:6px 14px;width:fit-content">
        🤖 Auto-processing in <strong id="countdown-val" style="color:var(--text);min-width:22px">—</strong> s
      </div>
      <div style="font-size:10px;color:var(--dim)">Agent also runs every 30s automatically — no action required</div>
    </div>`;
  document.getElementById('fhir-json').innerHTML = '<span style="color:var(--dim);font-size:12px">Waiting for results…</span>';
  document.getElementById('valid-body').innerHTML = '<div style="color:var(--dim);font-size:12px">Waiting for results…</div>';
  tickCountdown();
}}

function showProcessingState(doc) {{
  _showMainPanel('detail');
  _loadDocImage(doc.id);
  document.getElementById('summary-panel').innerHTML = `
    <div style="display:flex;flex-direction:column;gap:12px;padding:4px 0">
      <div style="display:flex;align-items:center;gap:8px;font-size:13px;font-weight:700;color:var(--text)">
        ⚙️ Processing — pipeline running
      </div>
      <div style="font-size:12px;color:var(--muted);line-height:1.6">
        The agent is running the 4-stage pipeline now.<br/>
        Results will appear here automatically when done.
      </div>
      <div style="display:flex;align-items:center;gap:8px;font-size:12px;color:#3b82f6">
        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#3b82f6;animation:pulse 1.2s infinite"></span>
        Live — watch the Activity Feed for stage updates
      </div>
      <button disabled
        style="background:#1e293b;border:1px solid var(--border);border-radius:10px;padding:12px 20px;
        color:var(--dim);font-size:13px;font-weight:700;cursor:not-allowed;width:100%">
        ⚙️ Processing…
      </button>
    </div>`;
  document.getElementById('fhir-json').innerHTML = '<span style="color:var(--dim);font-size:12px">Building FHIR bundle…</span>';
  document.getElementById('valid-body').innerHTML = '<div style="color:var(--dim);font-size:12px">Running safety checks…</div>';
}}

function showFailedState(doc) {{
  _showMainPanel('detail');
  _loadDocImage(doc.id);
  document.getElementById('summary-panel').innerHTML = `
    <div style="display:flex;flex-direction:column;gap:12px;padding:4px 0">
      <div style="font-size:13px;font-weight:700;color:#ef4444">❌ Processing Failed</div>
      <div style="font-size:12px;color:var(--muted);line-height:1.6">
        ${{esc(doc.error_message || 'An error occurred during pipeline execution.')}}
      </div>
      <button onclick="processNow()" id="process-now-btn"
        style="background:linear-gradient(135deg,#3b82f6,#8b5cf6);border:none;
        border-radius:10px;padding:12px 20px;color:#fff;font-size:13px;font-weight:700;
        cursor:pointer;width:100%">
        ↺ Retry Processing
      </button>
    </div>`;
  document.getElementById('fhir-json').innerHTML = '<span style="color:var(--dim);font-size:12px">No results — processing failed.</span>';
  document.getElementById('valid-body').innerHTML = '<div style="color:var(--dim);font-size:12px">No results — processing failed.</div>';
}}

// ── Process Now ──────────────────────────────────────────────────────────────
async function processNow() {{
  const btn = document.getElementById('process-now-btn');
  if (btn) {{ btn.disabled = true; btn.textContent = '⚙️ Triggering…'; }}
  try {{
    const r = await fetch('/agent/process-now', {{method: 'POST'}});
    if (r.ok) {{
      if (btn) btn.textContent = '✔ Triggered — watch activity feed';
      _lastPollTime = Date.now();
      if (_fastPollTimer) clearInterval(_fastPollTimer);
      _fastPollTimer = setInterval(() => {{ refreshAll(); refreshActivity(); }}, 2000);
      setTimeout(() => {{
        if (_fastPollTimer) {{ clearInterval(_fastPollTimer); _fastPollTimer = null; }}
      }}, 60000);
    }} else {{
      if (btn) {{ btn.disabled = false; btn.textContent = '▶ Process Now'; }}
    }}
  }} catch(e) {{
    if (btn) {{ btn.disabled = false; btn.textContent = '▶ Process Now'; }}
  }}
}}

async function loadDocResults(id) {{
  _showMainPanel('detail');
  _loadDocImage(id);

  const data = await fetchJ('/intake/' + id + '/results').catch(() => null);
  if (!data) return;

  renderSummary(data);
  renderFhir(data.fhir_bundle);
  renderValidation(data.validation, data.safety_flags);

  // Update header badge
  const val = data.validation || {{}};
  const passed = val.passed_count ?? 0;
  const total  = val.total_count ?? 0;
  const ok = val.overall_passed;
  const bc = ok ? 'var(--accent)' : 'var(--warn)';
  document.getElementById('detail-badge').innerHTML =
    `<span style="font-size:11px;font-weight:700;padding:4px 10px;border-radius:20px;
      background:${{bc}}18;color:${{bc}};border:1px solid ${{bc}}40">
      ${{ok ? '✓ PASSED' : '⚠ REVIEW'}} ${{passed}}/${{total}}
    </span>`;
}}

// ── Summary panel ────────────────────────────────────────────────────────────
function renderSummary(data) {{
  const ex = data.extraction_summary || {{}};
  const st = data.standardization    || {{}};
  const icd = st.icd10 || {{}};
  const conf = ex.overall_confidence;
  const confPct = conf != null ? (conf * 100).toFixed(0) + '%' : '—';
  const confColor = conf != null && conf > 0.8 ? 'var(--accent)' : 'var(--warn)';

  const flags = ex.flags || [];
  const sfFlags = st.safety_flags || [];

  document.getElementById('summary-panel').innerHTML = `
    <div class="sec-label" style="margin-top:0">Extraction Summary</div>
    <div class="summ-grid">
      <div class="summ-card">
        <div class="summ-card-label">Hospital</div>
        <div class="summ-card-val" title="${{esc(ex.hospital?.name||'')}}">${{esc(ex.hospital?.name||'—')}}</div>
      </div>
      <div class="summ-card">
        <div class="summ-card-label">Unit</div>
        <div class="summ-card-val">${{esc(ex.hospital?.unit||'—')}}</div>
      </div>
      <div class="summ-card">
        <div class="summ-card-label">Diagnosis</div>
        <div class="summ-card-val" title="${{esc(ex.diagnosis||'')}}">${{esc(ex.diagnosis||'—')}}</div>
      </div>
      <div class="summ-card">
        <div class="summ-card-label">ICD-10</div>
        <div class="summ-card-val" style="color:var(--accent);font-family:monospace">${{esc(icd.code||'—')}}</div>
      </div>
      <div class="summ-card">
        <div class="summ-card-label">Regimen</div>
        <div class="summ-card-val" style="color:var(--accent)">${{esc(ex.regimen||'—')}}</div>
      </div>
      <div class="summ-card">
        <div class="summ-card-label">Cycles</div>
        <div class="summ-card-val">${{ex.cycles_count ?? '—'}}</div>
      </div>
      <div class="summ-card">
        <div class="summ-card-label">Confidence</div>
        <div class="summ-card-val" style="color:${{confColor}}">${{confPct}}</div>
      </div>
      <div class="summ-card">
        <div class="summ-card-label">Patient ID</div>
        <div class="summ-card-val" style="font-family:monospace;font-size:10px;color:var(--dim)">${{esc((data.document?.id||'').slice(0,8)+'…')}}</div>
      </div>
    </div>
    ${{flags.length ? `
      <div class="sec-label">Vision Flags</div>
      <div class="flag-list">${{flags.map(f=>`<span class="flag-tag">${{esc(String(f))}}</span>`).join('')}}</div>
    ` : ''}}
    ${{sfFlags.length ? `
      <div class="sec-label" style="color:var(--warn)">Clinical Flags</div>
      ${{sfFlags.map(f=>`
        <div style="background:#f59e0b10;border:1px solid #f59e0b30;border-radius:6px;
          padding:7px 10px;margin-bottom:5px;font-size:11px">
          <span style="color:var(--warn);font-weight:700">${{f.severity}}</span>
          <span style="color:var(--muted);margin-left:6px">${{esc(f.description||'')}}</span>
        </div>
      `).join('')}}
    ` : ''}}
  `;
}}

// ── FHIR JSON viewer ─────────────────────────────────────────────────────────
function renderFhir(bundle) {{
  _fhirData = bundle;
  if (!bundle) {{
    document.getElementById('fhir-json').innerHTML = '<span style="color:var(--dim)">No FHIR data</span>';
    return;
  }}
  document.getElementById('fhir-json').innerHTML = syntaxHL(JSON.stringify(bundle, null, 2));
}}

function syntaxHL(json) {{
  return json
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"(dose_mg)":\s*(\d+\.?\d*)/g, (_, k, v) => {{}})  // handled below
    .replace(/"([^"]+)":/g, (_,k) => `"<span class="jk">${{k}}</span>":`)
    .replace(/: "([^"]*)"([,\\n])/g, (_,v,end) => {{
      const cls = /^[A-Z]\d{{2}}/.test(v) ? 'jicd' : 'js';
      return `: "<span class="${{cls}}">${{v}}</span>"${{end}}`;
    }})
    .replace(/: (\d+\.?\d*)([,\\n ])/g, (_,v,end) => `: <span class="jn">${{v}}</span>${{end}}`)
    .replace(/: (true|false)/g, (_,v) => `: <span class="jb">${{v}}</span>`)
    .replace(/: (null)/g, `_: <span class="jnull">null</span>`);
}}

function copyFhir() {{
  if (!_fhirData) return;
  navigator.clipboard.writeText(JSON.stringify(_fhirData, null, 2));
  const btn = document.querySelector('.copy-btn');
  btn.textContent = 'Copied!';
  setTimeout(() => btn.textContent = 'Copy JSON', 1500);
}}

// ── Validation panel ──────────────────────────────────────────────────────────
function renderValidation(val, dbFlags) {{
  if (!val || !val.checks) {{
    document.getElementById('valid-body').innerHTML = '<div style="color:var(--dim);font-size:12px">No validation data</div>';
    return;
  }}

  const passed = val.passed_count;
  const total  = val.total_count;
  document.getElementById('valid-badge').textContent = passed + '/' + total + ' passed';

  // Dose alert box if dose consistency failed
  const doseCheck = val.checks.find(c => c.name === 'Dose Consistency' && !c.passed);
  const doseAlert = doseCheck ? `
    <div class="dose-alert">
      <div class="dose-alert-title">⚠ CRITICAL: Dose Variance Detected</div>
      <div class="dose-alert-body">${{esc(doseCheck.detail)}}</div>
    </div>
  ` : '';

  const checksHtml = val.checks.map(c => `
    <div class="check-row ${{c.passed ? 'ok' : 'fail'}}">
      <span style="font-size:16px;flex-shrink:0">${{c.passed ? '✅' : '❌'}}</span>
      <div>
        <div class="check-name" style="color:${{c.passed ? 'var(--accent)' : 'var(--err)'}}">${{esc(c.name)}}</div>
        <div class="check-det">${{esc(c.detail)}}</div>
      </div>
    </div>
  `).join('');

  // DB flags
  const flagsHtml = dbFlags && dbFlags.length ? `
    <div class="sec-label" style="margin-top:14px">Raised Flags</div>
    ${{dbFlags.map(f => `
      <div style="background:var(--bg);border:1px solid #ef444430;border-radius:7px;
        padding:8px 10px;margin-bottom:5px;font-size:11px">
        <div style="font-weight:700;color:var(--err);font-size:10px;text-transform:uppercase;letter-spacing:.4px">
          ${{f.severity}} · ${{f.flag_type}}
        </div>
        <div style="color:var(--muted);margin-top:3px;line-height:1.4">${{esc(f.details)}}</div>
        ${{f.resolved ? '<div style="color:var(--accent);font-size:10px;margin-top:3px">✓ Resolved</div>' : ''}}
      </div>
    `).join('')}}
  ` : '';

  document.getElementById('valid-body').innerHTML = doseAlert + checksHtml + flagsHtml;
}}

// ── Upload ────────────────────────────────────────────────────────────────────
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');

dropZone.addEventListener('dragover', e => {{ e.preventDefault(); dropZone.classList.add('over'); }});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('over'));
dropZone.addEventListener('drop', e => {{ e.preventDefault(); dropZone.classList.remove('over'); uploadFiles(e.dataTransfer.files); }});
fileInput.addEventListener('change', () => {{ if (fileInput.files.length) uploadFiles(fileInput.files); fileInput.value=''; }});

async function uploadFiles(files) {{
  const arr = Array.from(files);
  setUploadStatus('loading', 'Uploading ' + arr.length + ' file' + (arr.length>1?'s':'') + '…');
  let ok=0, fail=0, lastId=null;
  for (const file of arr) {{
    try {{
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch('/intake', {{method:'POST', body:fd}});
      if (r.ok) {{ ok++; const d = await r.json(); lastId = d.document_id || lastId; }}
      else fail++;
    }} catch(e) {{ fail++; }}
  }}
  if (fail === 0) setUploadStatus('ok', '✓ ' + ok + ' doc' + (ok>1?'s':'') + ' queued — click "Process Now" or wait 30s');
  else setUploadStatus('err', ok + ' queued, ' + fail + ' failed');
  await refreshAll();
  // Auto-select the just-uploaded doc
  if (lastId) selectDoc(lastId);
}}

async function runSimulate() {{
  const btn = document.getElementById('sim-btn');
  btn.disabled = true;
  setUploadStatus('loading', 'Injecting test batch…');
  try {{
    const r = await fetch('/intake/simulate');
    const d = await r.json();
    setUploadStatus('ok', '✓ ' + d.queued_count + ' test docs injected — click "Process Now" or wait for auto-pickup');
    await refreshAll();
    // Auto-select the first injected doc
    const firstId = d.document_ids && d.document_ids[0];
    if (firstId) selectDoc(firstId);
  }} catch(e) {{
    setUploadStatus('err', 'Failed: ' + e.message);
  }} finally {{
    setTimeout(() => {{ btn.disabled = false; }}, 3000);
  }}
}}

function setUploadStatus(type, msg) {{
  const el = document.getElementById('upload-status');
  el.className = 'upload-status ' + (type==='ok'?'us-ok':type==='err'?'us-err':'us-loading');
  el.textContent = msg;
  if (type !== 'loading') setTimeout(() => {{ if (el.textContent === msg) el.textContent = ''; }}, 8000);
}}

// ── Activity feed ─────────────────────────────────────────────────────────────
async function refreshActivity() {{
  const data = await fetchJ('/agent/activity?limit=80').catch(() => null);
  if (!data) return;
  renderActivity(data.entries, data.has_active);
}}

function renderActivity(entries, hasActive) {{
  const scroll = document.getElementById('act-scroll');
  const bar    = document.getElementById('act-active-bar');
  const status = document.getElementById('act-status');

  status.textContent = entries.length + ' events';

  // Spinner bar when something is actively processing
  if (hasActive) {{
    bar.style.display = 'flex';
    const latest = entries.slice().reverse().find(e => e.event === 'stage_start');
    document.getElementById('act-active-msg').textContent =
      latest ? latest.message.replace('⏳ ','') : 'Processing…';
  }} else {{
    bar.style.display = 'none';
  }}

  if (!entries.length) {{
    scroll.innerHTML = '<div class="act-empty">Waiting for agent activity…</div>';
    return;
  }}

  const wasAtBottom = scroll.scrollHeight - scroll.scrollTop <= scroll.clientHeight + 40;

  scroll.innerHTML = entries.map(e => {{
    const lvl = e.level || 'info';
    const stageTag = e.stage ? `<span class="act-stage">${{esc(e.stage)}}</span>` : '';
    return `<div class="act-row level-${{lvl}}">
      <span class="act-ts">${{fmtTime(e.timestamp)}}</span>
      <span class="act-msg">${{esc(e.message)}}</span>
      ${{stageTag}}
    </div>`;
  }}).join('');

  // Auto-scroll to bottom when new entries arrive
  if (wasAtBottom) scroll.scrollTop = scroll.scrollHeight;
}}

// ── Uptime counter ────────────────────────────────────────────────────────────
function refreshUptime() {{
  if (!_startedAt) return;
  const s = Math.floor((Date.now() - _startedAt) / 1000);
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), sec = s%60;
  const str = h > 0 ? h+'h '+m+'m' : m > 0 ? m+'m '+sec+'s' : sec+'s';
  setText('kpi-uptime', str);
}}

// ── Utilities ─────────────────────────────────────────────────────────────────
function fmtTime(ts) {{
  if (!ts) return '—';
  try {{ return new Date(ts).toLocaleTimeString('en-US',{{hour:'2-digit',minute:'2-digit',second:'2-digit'}}); }}
  catch(e) {{ return ts; }}
}}
function statusColor(s) {{
  return {{pending:'#6b7280',processing:'#3b82f6',complete:'#22c55e',failed:'#ef4444'}}[s]||'#64748b';
}}
function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}
function setText(id, val) {{
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}}
async function fetchJ(url) {{
  const r = await fetch(url);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_ts(ts: str) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S UTC")
    except Exception:
        return ts


def _is_recent(ts: str, seconds: int) -> bool:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() < seconds
    except Exception:
        return False


def _format_uptime(started_at: str) -> str:
    try:
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        total = int(delta.total_seconds())
        h, remainder = divmod(total, 3600)
        m, s = divmod(remainder, 60)
        if h > 0:
            return f"{h}h {m}m"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"
    except Exception:
        return "—"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
