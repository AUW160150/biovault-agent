"""
BioVault Agent — Live Dashboard
---------------------------------
GET /dashboard — single-page, fully live dashboard.
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
    heartbeat   = db.get_heartbeat() or {}
    stats       = db.get_stats()
    started_at  = heartbeat.get("started_at", "")
    uptime_str  = _format_uptime(started_at)
    last_seen   = heartbeat.get("last_seen", "")
    agent_status   = "RUNNING" if _is_recent(last_seen, 90) else "STALLED"
    status_color   = "#22c55e" if agent_status == "RUNNING" else "#ef4444"
    status_bg      = "#22c55e18" if agent_status == "RUNNING" else "#ef444418"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>BioVault Agent · Clinical Watchdog</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet"/>
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    :root{{
      --bg:#060b18;
      --panel:#0b1120;
      --panel2:#080e1c;
      --card:#0f1729;
      --border:#1a2540;
      --border2:#243050;
      --accent:#00d4aa;
      --accent2:#00b894;
      --warn:#f59e0b;
      --err:#ef4444;
      --blue:#3b82f6;
      --blue2:#2563eb;
      --purple:#8b5cf6;
      --pink:#ec4899;
      --text:#e2e8f0;
      --text2:#cbd5e1;
      --muted:#64748b;
      --dim:#334155;
      --glow-blue:#3b82f630;
      --glow-accent:#00d4aa20;
    }}
    html,body{{height:100%;overflow:hidden;background:var(--bg);color:var(--text);
      font-family:'Inter','Segoe UI',system-ui,sans-serif;font-size:13px;
      -webkit-font-smoothing:antialiased}}

    /* ── Scrollbars ── */
    ::-webkit-scrollbar{{width:4px;height:4px}}
    ::-webkit-scrollbar-track{{background:transparent}}
    ::-webkit-scrollbar-thumb{{background:var(--border2);border-radius:4px}}
    ::-webkit-scrollbar-thumb:hover{{background:var(--muted)}}

    /* ── Layout ── */
    .app{{display:flex;height:100vh;overflow:hidden;
      background:radial-gradient(ellipse 80% 50% at 10% 0%,#0d1f3c55 0%,transparent 60%),
                 radial-gradient(ellipse 60% 40% at 90% 100%,#0a1a2e44 0%,transparent 60%),
                 var(--bg)}}
    .sidebar{{width:320px;min-width:200px;max-width:600px;display:flex;flex-direction:column;
      background:var(--panel);overflow:hidden;flex-shrink:0;
      border-right:1px solid var(--border)}}
    .resize-handle{{
      width:4px;flex-shrink:0;cursor:col-resize;background:transparent;
      transition:background .15s;position:relative;z-index:10
    }}
    .resize-handle:hover,.resize-handle.dragging{{background:var(--blue)}}
    .resize-handle::after{{
      content:'';position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
      width:2px;height:40px;border-radius:2px;
      background:var(--border2);transition:background .15s
    }}
    .resize-handle:hover::after,.resize-handle.dragging::after{{background:var(--blue)}}
    .main{{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}}

    /* ── Sidebar Header ── */
    .sidebar-hdr{{
      padding:16px 18px 14px;
      border-bottom:1px solid var(--border);
      background:linear-gradient(180deg,#0f1b35 0%,var(--panel) 100%);
      flex-shrink:0
    }}
    .logo{{display:flex;align-items:center;gap:11px;margin-bottom:12px}}
    .logo-icon{{
      width:38px;height:38px;border-radius:10px;flex-shrink:0;
      background:linear-gradient(135deg,var(--blue) 0%,var(--purple) 100%);
      display:flex;align-items:center;justify-content:center;font-size:20px;
      box-shadow:0 4px 16px #3b82f640
    }}
    .logo-text h1{{font-size:15px;font-weight:800;letter-spacing:-.4px;
      background:linear-gradient(90deg,#e2e8f0,#94a3b8);
      -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
    .logo-text p{{font-size:10px;color:var(--muted);margin-top:1px;letter-spacing:.2px}}
    .agent-badge{{
      display:flex;align-items:center;gap:8px;
      background:{status_bg};border:1px solid {status_color}30;
      border-radius:8px;padding:7px 12px
    }}
    .pulse{{width:8px;height:8px;border-radius:50%;background:{status_color};flex-shrink:0;
      box-shadow:0 0 0 0 {status_color}66;animation:pulse-ring 2s infinite}}
    @keyframes pulse-ring{{
      0%{{box-shadow:0 0 0 0 {status_color}66}}
      70%{{box-shadow:0 0 0 6px transparent}}
      100%{{box-shadow:0 0 0 0 transparent}}
    }}
    .badge-inner{{flex:1}}
    .badge-status{{font-size:11px;font-weight:700;color:{status_color};letter-spacing:.4px}}
    .badge-hb{{font-size:10px;color:var(--muted);margin-top:1px}}
    .badge-uptime{{
      font-size:10px;font-weight:600;
      background:var(--blue)18;color:var(--blue);
      border:1px solid var(--blue)30;border-radius:5px;
      padding:2px 7px
    }}

    /* ── Sidebar body ── */
    .sidebar-body{{flex:1;overflow-y:auto;padding:14px 16px}}

    /* ── Section labels ── */
    .sec-label{{
      font-size:9.5px;font-weight:700;text-transform:uppercase;
      letter-spacing:1px;color:var(--muted);
      margin-bottom:9px;margin-top:18px;
      display:flex;align-items:center;gap:6px
    }}
    .sec-label:first-child{{margin-top:0}}
    .sec-label::after{{content:'';flex:1;height:1px;background:var(--border)}}

    /* ── Upload zone ── */
    .drop-zone{{
      border:1.5px dashed var(--border2);border-radius:12px;
      background:var(--card);padding:18px 14px;text-align:center;cursor:pointer;
      transition:all .2s;position:relative;margin-bottom:8px;
      background:linear-gradient(135deg,var(--card) 0%,#0d1420 100%)
    }}
    .drop-zone:hover{{border-color:var(--blue);background:var(--glow-blue);
      box-shadow:0 0 0 3px var(--glow-blue)}}
    .drop-zone.over{{border-color:var(--accent);background:var(--glow-accent);
      box-shadow:0 0 0 3px var(--glow-accent)}}
    .drop-zone input[type=file]{{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}}
    .drop-icon{{font-size:22px;margin-bottom:5px;opacity:.8}}
    .drop-text{{font-size:11.5px;color:var(--text2)}}
    .drop-text strong{{color:var(--text);font-weight:600}}
    .drop-hint{{font-size:10px;color:var(--muted);margin-top:3px}}

    .sim-btn{{
      width:100%;background:linear-gradient(135deg,#1a0f35,#1a1035);
      border:1px solid var(--purple)40;border-radius:10px;padding:10px;cursor:pointer;
      color:var(--purple);font-size:11.5px;font-weight:600;font-family:'Inter',sans-serif;
      transition:all .2s;display:flex;align-items:center;justify-content:center;gap:7px
    }}
    .sim-btn:hover{{border-color:var(--purple);background:linear-gradient(135deg,#1e1040,#1e1045);
      box-shadow:0 0 12px var(--purple)22}}
    .sim-btn:disabled{{opacity:.4;cursor:not-allowed}}

    .upload-status{{font-size:11px;min-height:16px;margin-top:6px;text-align:center;
      padding:0 4px;line-height:1.4}}
    .us-ok{{color:var(--accent)}}.us-err{{color:var(--err)}}.us-loading{{color:var(--blue)}}

    /* ── KPI cards ── */
    .kpi-grid{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:6px}}
    .kpi{{
      background:var(--card);border:1px solid var(--border);
      border-radius:10px;padding:11px 13px;position:relative;overflow:hidden;
      transition:border-color .2s
    }}
    .kpi::before{{
      content:'';position:absolute;inset:0;opacity:.04;
      background:linear-gradient(135deg,white,transparent)
    }}
    .kpi-val{{font-size:24px;font-weight:800;letter-spacing:-1px;line-height:1;
      font-variant-numeric:tabular-nums}}
    .kpi-lbl{{font-size:9.5px;color:var(--muted);margin-top:3px;
      text-transform:uppercase;letter-spacing:.6px;font-weight:500}}
    .c-green{{color:#22c55e}}.c-red{{color:var(--err)}}.c-blue{{color:var(--blue)}}
    .c-yellow{{color:var(--warn)}}.c-accent{{color:var(--accent)}}.c-muted{{color:var(--muted)}}

    /* ── Queue status strip ── */
    .q-strip{{
      display:flex;gap:0;background:var(--card);border:1px solid var(--border);
      border-radius:10px;overflow:hidden;margin-bottom:6px
    }}
    .q-seg{{flex:1;padding:8px 6px;text-align:center;border-right:1px solid var(--border)}}
    .q-seg:last-child{{border-right:none}}
    .q-num{{font-size:16px;font-weight:700;font-variant-numeric:tabular-nums}}
    .q-lbl{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-top:2px}}

    /* ── Alerts compact ── */
    .alert-item{{
      background:linear-gradient(135deg,#1a080808,#150b0b);
      border:1px solid #ef444430;border-left:3px solid var(--err);
      border-radius:8px;padding:8px 10px;margin-bottom:5px
    }}
    .alert-sev{{font-weight:700;color:var(--err);font-size:9.5px;
      text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px}}
    .alert-det{{color:var(--muted);line-height:1.45;font-size:11px}}

    /* ── Document list ── */
    .doc-item{{
      display:flex;align-items:center;gap:10px;padding:8px 10px;
      border-radius:10px;cursor:pointer;
      transition:all .15s;border:1px solid transparent;margin-bottom:4px
    }}
    .doc-item:hover{{background:var(--card);border-color:var(--border)}}
    .doc-item.active{{
      background:linear-gradient(135deg,#0f1e38,#111830);
      border-color:var(--blue)50;
      box-shadow:0 2px 12px var(--glow-blue)
    }}
    .doc-thumb{{width:36px;height:36px;border-radius:7px;object-fit:cover;
      border:1px solid var(--border);background:var(--border);flex-shrink:0}}
    .doc-thumb-ph{{width:36px;height:36px;border-radius:7px;
      background:var(--card);border:1px solid var(--border);flex-shrink:0;
      display:flex;align-items:center;justify-content:center;
      font-size:15px;color:var(--muted)}}
    .doc-info{{flex:1;min-width:0}}
    .doc-name{{font-size:11.5px;font-weight:500;white-space:nowrap;
      overflow:hidden;text-overflow:ellipsis;color:var(--text)}}
    .doc-meta{{display:flex;align-items:center;gap:5px;margin-top:3px;flex-wrap:wrap}}
    .status-pill{{
      display:inline-flex;align-items:center;padding:1px 7px;border-radius:20px;
      font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.4px
    }}
    .doc-time{{font-size:9.5px;color:var(--muted)}}

    /* ── Main panel ── */
    .main-hdr{{
      display:flex;align-items:center;justify-content:space-between;
      padding:12px 20px;border-bottom:1px solid var(--border);flex-shrink:0;
      background:linear-gradient(180deg,#0c1428 0%,var(--panel) 100%);min-height:52px
    }}
    .main-hdr-left{{display:flex;flex-direction:column;gap:2px;min-width:0}}
    .main-hdr-title{{font-size:13px;font-weight:600;color:var(--text);
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
    .main-hdr-sub{{font-size:10.5px;color:var(--muted)}}

    /* ── Activity feed ── */
    .activity-panel{{
      flex-shrink:0;border-bottom:1px solid var(--border);
      display:flex;flex-direction:column;height:170px;
      background:var(--panel)
    }}
    .act-hdr{{
      display:flex;align-items:center;justify-content:space-between;
      padding:8px 16px;border-bottom:1px solid var(--border);flex-shrink:0
    }}
    .act-hdr-title{{font-size:11px;font-weight:600;color:var(--text);
      display:flex;align-items:center;gap:6px}}
    .act-scroll{{flex:1;overflow-y:auto;padding:4px 0}}
    .act-row{{
      display:flex;align-items:baseline;gap:8px;
      padding:2.5px 16px;font-size:11px;line-height:1.5;
      transition:background .1s;position:relative
    }}
    .act-row::before{{
      content:'';position:absolute;left:8px;top:50%;transform:translateY(-50%);
      width:4px;height:4px;border-radius:50%;background:var(--border2)
    }}
    .act-row:hover{{background:#ffffff04}}
    .act-row.level-success::before{{background:var(--accent)}}
    .act-row.level-warn::before{{background:var(--warn)}}
    .act-row.level-error::before{{background:var(--err)}}
    .act-row.level-info::before{{background:var(--blue)40}}
    .act-ts{{color:var(--muted);font-size:9.5px;font-family:'Fira Code',monospace;
      flex-shrink:0;width:58px;margin-left:6px}}
    .act-msg{{color:var(--text2);flex:1}}
    .act-stage{{font-size:9.5px;color:var(--dim);flex-shrink:0;font-family:'Fira Code',monospace}}
    .act-active{{
      display:flex;align-items:center;gap:6px;
      padding:3px 16px 5px;font-size:10.5px;color:var(--accent)
    }}
    .act-spinner{{
      display:inline-block;width:7px;height:7px;border-radius:50%;flex-shrink:0;
      border:1.5px solid var(--accent)44;border-top-color:var(--accent);
      animation:spin .7s linear infinite
    }}
    @keyframes spin{{to{{transform:rotate(360deg)}}}}
    .act-empty{{
      display:flex;align-items:center;justify-content:center;
      height:100%;font-size:11px;color:var(--muted)
    }}

    /* ── Empty state ── */
    .empty-state{{
      flex:1;display:flex;flex-direction:column;
      align-items:center;justify-content:center;gap:10px;
      background:radial-gradient(ellipse 60% 40% at 50% 50%,#0d1f3c22 0%,transparent 70%)
    }}
    .empty-icon{{font-size:52px;opacity:.15}}
    .empty-title{{font-size:14px;font-weight:600;color:var(--muted)}}
    .empty-sub{{font-size:11px;color:var(--dim);text-align:center;max-width:280px;line-height:1.6}}

    /* ── Detail view ── */
    .detail{{flex:1;display:flex;overflow:hidden}}
    .detail-left{{
      width:230px;flex-shrink:0;
      border-right:1px solid var(--border);
      background:var(--panel2);display:flex;flex-direction:column
    }}
    .detail-left img{{width:100%;flex:1;object-fit:contain;padding:10px;min-height:0}}
    .detail-right{{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}}

    /* ── Tab bar ── */
    .tab-bar{{
      display:flex;border-bottom:1px solid var(--border);
      background:var(--panel);flex-shrink:0;padding:0 4px
    }}
    .tab-btn{{
      padding:10px 16px;font-size:11.5px;font-weight:600;cursor:pointer;
      color:var(--muted);border:none;background:none;
      border-bottom:2px solid transparent;margin-bottom:-1px;
      transition:all .15s;font-family:'Inter',sans-serif;white-space:nowrap
    }}
    .tab-btn:hover{{color:var(--text2)}}
    .tab-btn.active{{
      color:var(--blue);
      border-bottom-color:var(--blue)
    }}
    .tab-content{{flex:1;overflow:hidden;display:none;flex-direction:column}}
    .tab-content.active{{display:flex}}

    /* ── Overview tab ── */
    .overview-body{{flex:1;overflow-y:auto;padding:14px 16px}}
    .summ-grid{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:12px}}
    .summ-card{{
      background:var(--card);border:1px solid var(--border);
      border-radius:9px;padding:10px 12px;
      transition:border-color .15s
    }}
    .summ-card:hover{{border-color:var(--border2)}}
    .summ-card-label{{
      font-size:9px;text-transform:uppercase;letter-spacing:.7px;
      color:var(--muted);margin-bottom:4px;font-weight:600
    }}
    .summ-card-val{{
      font-size:12.5px;font-weight:600;color:var(--text);
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis
    }}
    .flag-tag{{
      display:inline-block;background:#f59e0b14;border:1px solid #f59e0b35;
      color:var(--warn);border-radius:5px;padding:2px 8px;font-size:9.5px;
      margin:2px 3px 2px 0
    }}

    /* ── FHIR tab ── */
    .fhir-toolbar{{
      display:flex;align-items:center;justify-content:space-between;
      padding:8px 16px;border-bottom:1px solid var(--border);flex-shrink:0;
      background:var(--panel)
    }}
    .fhir-label{{font-size:11px;font-weight:600;color:var(--muted)}}
    .copy-btn{{
      font-size:10px;padding:4px 10px;border-radius:6px;cursor:pointer;
      color:var(--accent);border:1px solid var(--accent)35;background:transparent;
      transition:all .15s;font-family:'Inter',sans-serif
    }}
    .copy-btn:hover{{background:var(--glow-accent);border-color:var(--accent)60}}
    .json-view{{
      flex:1;overflow-y:auto;padding:12px 16px;
      background:var(--panel2);
      font-family:'Fira Code','Courier New',monospace;
      font-size:11px;line-height:1.7;white-space:pre
    }}
    .jk{{color:#7dd3fc}}.js{{color:#86efac}}.jn{{color:#fca5a5}}
    .jb{{color:#c4b5fd}}.jnull{{color:var(--dim)}}.jicd{{color:var(--accent);font-weight:600}}

    /* ── Safety tab ── */
    .safety-body{{flex:1;overflow-y:auto;padding:12px 14px}}
    .dose-alert{{
      background:linear-gradient(135deg,#2a080812,#1a060612);
      border:1px solid #ef444440;border-left:3px solid var(--err);
      border-radius:9px;padding:12px 14px;margin-bottom:12px
    }}
    .dose-alert-title{{font-size:11.5px;font-weight:700;color:var(--err);margin-bottom:5px;
      display:flex;align-items:center;gap:6px}}
    .dose-alert-body{{font-size:11px;color:var(--muted);line-height:1.55}}
    .check-row{{
      display:flex;align-items:flex-start;gap:10px;padding:10px 12px;
      border-radius:9px;margin-bottom:5px;transition:background .15s
    }}
    .check-row.ok{{
      background:linear-gradient(135deg,#00d4aa08,#00b89404);
      border:1px solid var(--accent)20
    }}
    .check-row.fail{{
      background:linear-gradient(135deg,#ef444408,#dc262608);
      border:1px solid var(--err)25
    }}
    .check-row:hover{{filter:brightness(1.1)}}
    .check-icon{{font-size:14px;flex-shrink:0;margin-top:1px}}
    .check-name{{font-size:11.5px;font-weight:600;margin-bottom:2px}}
    .check-det{{font-size:10.5px;color:var(--muted);line-height:1.45}}
    .raised-flag{{
      background:var(--card);border:1px solid #ef444330;
      border-radius:8px;padding:9px 11px;margin-bottom:5px
    }}
    .raised-flag-type{{
      font-weight:700;color:var(--err);font-size:9.5px;
      text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px
    }}
    .raised-flag-det{{color:var(--muted);font-size:10.5px;line-height:1.45}}

    /* ── Pending / Processing states (in overview-body) ── */
    .state-card{{
      background:var(--card);border:1px solid var(--border);
      border-radius:12px;padding:20px;margin-bottom:12px
    }}
    .state-title{{font-size:13px;font-weight:700;margin-bottom:8px;
      display:flex;align-items:center;gap:8px}}
    .state-sub{{font-size:11.5px;color:var(--muted);line-height:1.6;margin-bottom:14px}}
    .process-btn{{
      width:100%;background:linear-gradient(135deg,var(--blue),var(--purple));
      border:none;border-radius:10px;padding:12px 20px;
      color:#fff;font-size:13px;font-weight:700;cursor:pointer;
      font-family:'Inter',sans-serif;transition:opacity .2s;
      display:flex;align-items:center;justify-content:center;gap:8px
    }}
    .process-btn:hover{{opacity:.88}}
    .process-btn:disabled{{opacity:.4;cursor:not-allowed}}
    .countdown-chip{{
      display:inline-flex;align-items:center;gap:6px;
      background:var(--bg);border:1px solid var(--border);
      border-radius:20px;padding:5px 12px;font-size:11px;
      color:var(--muted);margin-top:10px
    }}
    .countdown-chip strong{{color:var(--text);font-variant-numeric:tabular-nums;min-width:20px}}
    .auto-note{{font-size:9.5px;color:var(--dim);margin-top:8px;
      display:flex;align-items:center;gap:5px}}

    /* ── Image caption ── */
    .img-caption{{
      padding:7px 10px;border-top:1px solid var(--border);flex-shrink:0;
      background:var(--card)
    }}
    .img-caption-name{{font-size:10px;font-weight:600;color:var(--text2);
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
    .img-caption-meta{{font-size:9.5px;color:var(--muted);margin-top:1px}}

    /* ── Footer ── */
    .footer{{
      flex-shrink:0;padding:5px 20px;border-top:1px solid var(--border);
      font-size:9.5px;color:var(--muted);display:flex;align-items:center;
      justify-content:space-between;background:var(--panel)
    }}
    .footer a{{color:var(--blue);text-decoration:none}}
    .footer a:hover{{text-decoration:underline}}

  </style>
</head>
<body>
<div class="app">

<!-- ══════════════════ LEFT SIDEBAR ══════════════════ -->
<div class="sidebar">

  <div class="sidebar-hdr">
    <div class="logo">
      <div class="logo-icon">🧬</div>
      <div class="logo-text">
        <h1>BioVault Agent</h1>
        <p>Clinical Document Watchdog</p>
      </div>
    </div>
    <div class="agent-badge">
      <div class="pulse" id="pulse-dot"></div>
      <div class="badge-inner">
        <div class="badge-status" id="agent-status">{agent_status}</div>
        <div class="badge-hb" id="hb-ts">heartbeat —</div>
      </div>
      <div class="badge-uptime" id="kpi-uptime">{uptime_str}</div>
    </div>
  </div>

  <div class="sidebar-body">

    <div class="sec-label">Upload</div>
    <div class="drop-zone" id="drop-zone">
      <input type="file" id="file-input"
        accept="image/jpeg,image/png,image/webp,image/gif,application/pdf" multiple/>
      <div class="drop-icon">📄</div>
      <div class="drop-text"><strong>Click to upload</strong> or drag &amp; drop</div>
      <div class="drop-hint">JPEG · PNG · WebP · PDF &nbsp;|&nbsp; max 20 MB</div>
    </div>
    <button class="sim-btn" id="sim-btn" onclick="runSimulate()">
      ⚗️&nbsp; Inject Test Batch (5 docs)
    </button>
    <div class="upload-status" id="upload-status"></div>

    <div class="sec-label">Live Stats</div>
    <div class="kpi-grid">
      <div class="kpi">
        <div class="kpi-val c-green" id="kpi-processed">—</div>
        <div class="kpi-lbl">Processed</div>
      </div>
      <div class="kpi">
        <div class="kpi-val c-red" id="kpi-flags">—</div>
        <div class="kpi-lbl">Flags Raised</div>
      </div>
      <div class="kpi">
        <div class="kpi-val c-yellow" id="kpi-pending">—</div>
        <div class="kpi-lbl">In Queue</div>
      </div>
      <div class="kpi">
        <div class="kpi-val c-blue" id="kpi-complete">—</div>
        <div class="kpi-lbl">Complete</div>
      </div>
    </div>

    <div class="q-strip">
      <div class="q-seg">
        <div class="q-num" id="q-pending" style="color:#6b7280">0</div>
        <div class="q-lbl">Pending</div>
      </div>
      <div class="q-seg">
        <div class="q-num" id="q-proc" style="color:var(--blue)">0</div>
        <div class="q-lbl">Active</div>
      </div>
      <div class="q-seg">
        <div class="q-num" id="q-done" style="color:#22c55e">0</div>
        <div class="q-lbl">Done</div>
      </div>
      <div class="q-seg">
        <div class="q-num" id="q-fail" style="color:var(--err)">0</div>
        <div class="q-lbl">Failed</div>
      </div>
    </div>

    <div id="alerts-section"></div>

    <div class="sec-label">Documents</div>
    <div id="doc-list">
      <div style="color:var(--muted);font-size:11px;text-align:center;padding:24px 0;line-height:1.6">
        No documents yet<br/>
        <span style="color:var(--dim)">Upload one or inject a test batch</span>
      </div>
    </div>

  </div>
</div>

<div class="resize-handle" id="resize-handle" title="Drag to resize · Double-click to reset"></div>

<!-- ══════════════════ MAIN PANEL ══════════════════ -->
<div class="main">

  <div class="main-hdr">
    <div class="main-hdr-left">
      <div class="main-hdr-title" id="detail-title">Select a document</div>
      <div class="main-hdr-sub" id="detail-sub">Upload or inject a test batch to get started</div>
    </div>
    <div id="detail-badge"></div>
  </div>

  <!-- Activity Feed -->
  <div class="activity-panel">
    <div class="act-hdr">
      <div class="act-hdr-title">
        <span style="color:var(--blue)">⚡</span> Agent Activity
      </div>
      <div id="act-status" style="font-size:10px;color:var(--muted)">—</div>
    </div>
    <div id="act-active-bar" style="display:none" class="act-active">
      <span class="act-spinner"></span>
      <span id="act-active-msg">Processing…</span>
    </div>
    <div class="act-scroll" id="act-scroll">
      <div class="act-empty">Waiting for agent activity…</div>
    </div>
  </div>

  <!-- Empty state -->
  <div class="empty-state" id="empty-state">
    <div class="empty-icon">🧬</div>
    <div class="empty-title">No document selected</div>
    <div class="empty-sub">Upload a clinical document or inject a test batch from the sidebar, then click it to inspect results</div>
  </div>

  <!-- Detail view -->
  <div class="detail" id="detail-view" style="display:none">

    <!-- Left: persistent image -->
    <div class="detail-left">
      <img id="doc-img" src="" alt="Document"
        onerror="this.style.display='none';document.getElementById('img-ph').style.display='flex'"
        style="flex:1"/>
      <div id="img-ph" style="display:none;flex:1;align-items:center;justify-content:center;
        font-size:40px;color:var(--border2)">📄</div>
      <div class="img-caption">
        <div class="img-caption-name" id="img-caption-name">—</div>
        <div class="img-caption-meta" id="img-caption-meta">—</div>
      </div>
    </div>

    <!-- Right: tabs -->
    <div class="detail-right">
      <div class="tab-bar">
        <button class="tab-btn active" onclick="switchTab('overview')"  id="tab-btn-overview">📊 Overview</button>
        <button class="tab-btn"        onclick="switchTab('fhir')"      id="tab-btn-fhir">📋 FHIR R4</button>
        <button class="tab-btn"        onclick="switchTab('safety')"    id="tab-btn-safety">🛡️ Safety</button>
      </div>

      <!-- Overview tab -->
      <div class="tab-content active" id="tab-overview">
        <div class="overview-body" id="summary-panel">
          <div style="color:var(--muted);font-size:11px">Loading…</div>
        </div>
      </div>

      <!-- FHIR tab -->
      <div class="tab-content" id="tab-fhir">
        <div class="fhir-toolbar">
          <div class="fhir-label">FHIR R4 Bundle — JSON</div>
          <button class="copy-btn" onclick="copyFhir()">Copy JSON</button>
        </div>
        <div class="json-view" id="fhir-json">
          <span style="color:var(--muted)">Processing…</span>
        </div>
      </div>

      <!-- Safety tab -->
      <div class="tab-content" id="tab-safety">
        <div class="safety-body" id="valid-body">
          <div style="color:var(--muted);font-size:11px">Processing…</div>
        </div>
      </div>

    </div><!-- /detail-right -->
  </div><!-- /detail-view -->

  <div class="footer">
    <span id="footer-ts">⟳ live · refreshes every 8s</span>
    <span>
      <a href="/docs">API Docs</a> &nbsp;·&nbsp;
      <a href="/alerts">Alerts</a> &nbsp;·&nbsp;
      <a href="/health">Health</a> &nbsp;·&nbsp;
      <a href="https://akash.network" target="_blank">Akash Network</a>
    </span>
  </div>

</div><!-- /main -->
</div><!-- /app -->

<script>
let _selectedDocId = null;
let _fhirData      = null;
let _docs          = [];
let _startedAt     = null;
let _activeTab     = 'overview';

// ── Sidebar resize ────────────────────────────────────────────────────────────
(function() {{
  const handle  = document.getElementById('resize-handle');
  const sidebar = document.querySelector('.sidebar');
  const MIN_W = 200, MAX_W = 620, KEY = 'bv_sidebar_w';
  const saved = localStorage.getItem(KEY);
  if (saved) sidebar.style.width = saved + 'px';
  let dragging = false, startX = 0, startW = 0;
  handle.addEventListener('mousedown', e => {{
    dragging = true; startX = e.clientX;
    startW = sidebar.getBoundingClientRect().width;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  }});
  document.addEventListener('mousemove', e => {{
    if (!dragging) return;
    sidebar.style.width = Math.min(MAX_W, Math.max(MIN_W, startW + e.clientX - startX)) + 'px';
  }});
  document.addEventListener('mouseup', () => {{
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    localStorage.setItem(KEY, Math.round(sidebar.getBoundingClientRect().width));
  }});
  handle.addEventListener('dblclick', () => {{
    sidebar.style.width = '320px';
    localStorage.removeItem(KEY);
  }});
}})();

// ── Tab switching ────────────────────────────────────────────────────────────
function switchTab(tab) {{
  _activeTab = tab;
  ['overview','fhir','safety'].forEach(t => {{
    document.getElementById('tab-' + t).classList.toggle('active', t === tab);
    document.getElementById('tab-btn-' + t).classList.toggle('active', t === tab);
  }});
}}

// ── Bootstrap ────────────────────────────────────────────────────────────────
let _fastPollTimer = null;
let _lastPollTime  = Date.now();
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
  if (document.getElementById('act-active-bar').style.display !== 'none') {{
    const queue = await fetchJ('/intake/queue').catch(() => null);
    if (queue) updateQueue(queue);
    if (_selectedDocId) {{
      const sel = (_docs || []).find(d => d.id === _selectedDocId);
      if (sel && sel.status === 'complete') loadDocResults(_selectedDocId);
    }}
  }}
}}

function tickCountdown() {{
  if (!_selectedDocId) return;
  const sel = (_docs || []).find(d => d.id === _selectedDocId);
  if (!sel || sel.status !== 'pending') return;
  const remaining = Math.max(0, POLL_INTERVAL_S - Math.floor((Date.now() - _lastPollTime) / 1000));
  const el = document.getElementById('countdown-val');
  if (el) el.textContent = remaining;
}}

// ── Master refresh ────────────────────────────────────────────────────────────
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
  setText('footer-ts', '⟳ last refresh ' + new Date().toLocaleTimeString());

  if (_selectedDocId) {{
    const sel = (_docs || []).find(d => d.id === _selectedDocId);
    if (sel) {{
      if      (sel.status === 'complete')   loadDocResults(_selectedDocId);
      else if (sel.status === 'processing') showProcessingState(sel);
      else if (sel.status === 'pending')    showPendingState(sel);
      else if (sel.status === 'failed')     showFailedState(sel);
    }}
  }}
  if (!_selectedDocId && _docs.length) selectDoc(_docs[0].id);
}}

// ── Health ────────────────────────────────────────────────────────────────────
function updateHealth(h) {{
  setText('kpi-processed', h.documents_processed_total ?? 0);
  const flags = h.flags_raised_total ?? 0;
  setText('kpi-flags', flags);
  document.getElementById('kpi-flags').className = 'kpi-val ' + (flags > 0 ? 'c-red' : 'c-muted');
  const running = h.status === 'running';
  setText('agent-status', running ? 'RUNNING' : 'STALLED');
  const sc = running ? '#22c55e' : '#ef4444';
  document.getElementById('agent-status').style.color = sc;
  document.getElementById('pulse-dot').style.background = sc;
  if (h.heartbeat) setText('hb-ts', 'heartbeat ' + fmtTime(h.heartbeat));
  if (h.started_at && !_startedAt) _startedAt = new Date(h.started_at);
}}

// ── Queue ─────────────────────────────────────────────────────────────────────
function updateQueue(q) {{
  const s = q.stats || {{}};
  setText('q-pending',  s.pending    ?? 0);
  setText('q-proc',     s.processing ?? 0);
  setText('q-done',     s.complete   ?? 0);
  setText('q-fail',     s.failed     ?? 0);
  setText('kpi-pending', s.pending   ?? 0);
  setText('kpi-complete', s.complete ?? 0);
  _docs = q.recent_documents || [];
  renderDocList(_docs);
}}

// ── Alerts ────────────────────────────────────────────────────────────────────
function updateAlerts(a) {{
  const alerts = a.alerts || [];
  const sec = document.getElementById('alerts-section');
  if (!alerts.length) {{ sec.innerHTML = ''; return; }}
  sec.innerHTML = `
    <div class="sec-label" style="color:var(--err);margin-top:14px">⚠ Alerts (${{alerts.length}})</div>
    ${{alerts.slice(0,3).map(f => `
      <div class="alert-item">
        <div class="alert-sev">${{f.severity}} · ${{f.flag_type}}</div>
        <div class="alert-det">${{esc(f.details.slice(0,100))}}${{f.details.length>100?'…':''}}</div>
        <div style="font-size:9.5px;color:var(--muted);margin-top:3px">${{f.filename||''}} · ${{fmtTime(f.timestamp)}}</div>
      </div>
    `).join('')}}
    ${{alerts.length > 3 ? `<div style="font-size:10px;color:var(--muted);text-align:center;padding:4px 0">
      +${{alerts.length-3}} more — <a href="/alerts" style="color:var(--blue)">view all</a></div>` : ''}}
  `;
}}

// ── Document list ─────────────────────────────────────────────────────────────
function renderDocList(docs) {{
  const el = document.getElementById('doc-list');
  if (!docs.length) {{
    el.innerHTML = `<div style="color:var(--muted);font-size:11px;text-align:center;padding:24px 0;line-height:1.6">
      No documents yet<br/><span style="color:var(--dim)">Upload one or inject a test batch</span></div>`;
    return;
  }}
  el.innerHTML = docs.map(d => {{
    const sc = statusColor(d.status);
    const isActive = d.id === _selectedDocId;
    return `
      <div class="doc-item ${{isActive ? 'active' : ''}}" onclick="selectDoc('${{d.id}}')" id="di-${{d.id}}">
        <img class="doc-thumb" src="/intake/${{d.id}}/image"
          onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" style="display:block"/>
        <div class="doc-thumb-ph" style="display:none">📄</div>
        <div class="doc-info">
          <div class="doc-name" title="${{esc(d.filename)}}">${{esc(d.filename)}}</div>
          <div class="doc-meta">
            <span class="status-pill" style="background:${{sc}}18;color:${{sc}};border:1px solid ${{sc}}35">${{d.status}}</span>
            ${{d.critical_flags_count > 0 ? `<span style="background:var(--err)18;color:var(--err);border:1px solid var(--err)30;border-radius:20px;padding:1px 7px;font-size:9px;font-weight:700">⚠ ${{d.critical_flags_count}}</span>` : ''}}
          </div>
          <div class="doc-time">${{fmtTime(d.uploaded_at)}}</div>
        </div>
      </div>`;
  }}).join('');
}}

// ── Select doc ────────────────────────────────────────────────────────────────
async function selectDoc(id) {{
  _selectedDocId = id;
  document.querySelectorAll('.doc-item').forEach(el => el.classList.remove('active'));
  const row = document.getElementById('di-' + id);
  if (row) row.classList.add('active');
  const doc = _docs.find(d => d.id === id);
  if (!doc) return;
  setText('detail-title', doc.filename);
  setText('img-caption-name', doc.filename);
  setText('img-caption-meta', 'Uploaded ' + fmtTime(doc.uploaded_at));
  const sc = statusColor(doc.status);
  document.getElementById('detail-badge').innerHTML =
    `<span class="status-pill" style="background:${{sc}}18;color:${{sc}};border:1px solid ${{sc}}35;padding:4px 12px;font-size:11px">${{doc.status}}</span>`;
  document.getElementById('detail-sub').textContent =
    doc.processed_at ? 'Processed ' + fmtTime(doc.processed_at) :
    doc.uploaded_at  ? 'Uploaded '  + fmtTime(doc.uploaded_at)  : '';
  if      (doc.status === 'pending')    showPendingState(doc);
  else if (doc.status === 'processing') showProcessingState(doc);
  else if (doc.status === 'failed')     showFailedState(doc);
  else if (doc.status === 'complete')   loadDocResults(id);
}}

function _showDetail() {{
  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('detail-view').style.display = 'flex';
}}

function _loadDocImage(id) {{
  const img = document.getElementById('doc-img');
  const ph  = document.getElementById('img-ph');
  if (!img) return;
  img.src = '/intake/' + id + '/image?' + Date.now();
  img.style.display = '';
  if (ph) ph.style.display = 'none';
}}

// ── State panels ─────────────────────────────────────────────────────────────
function showPendingState(doc) {{
  _showDetail(); _loadDocImage(doc.id); switchTab('overview');
  document.getElementById('summary-panel').innerHTML = `
    <div class="state-card">
      <div class="state-title">🕐 Queued for Processing</div>
      <div class="state-sub">
        The autonomous agent will pick this document up automatically.
        Every 30 seconds it polls for pending documents — or click below to process immediately.
      </div>
      <button onclick="processNow()" id="process-now-btn" class="process-btn">
        ▶&nbsp; Process Now
      </button>
      <div class="countdown-chip">
        🤖 Auto-processing in <strong id="countdown-val">—</strong> s
      </div>
      <div class="auto-note">⚙ Agent runs every 30s autonomously — no action required</div>
    </div>`;
  document.getElementById('fhir-json').innerHTML = '<span style="color:var(--muted)">Waiting for results…</span>';
  document.getElementById('valid-body').innerHTML = '<div style="color:var(--muted);font-size:11px">Waiting for results…</div>';
  tickCountdown();
}}

function showProcessingState(doc) {{
  _showDetail(); _loadDocImage(doc.id); switchTab('overview');
  document.getElementById('summary-panel').innerHTML = `
    <div class="state-card">
      <div class="state-title">
        <span class="act-spinner" style="width:10px;height:10px;border-width:2px"></span>
        Pipeline Running
      </div>
      <div class="state-sub">
        The agent is processing this document through the 4-stage pipeline now.<br/>
        Results appear automatically when complete — watch the Activity Feed above.
      </div>
      <button disabled class="process-btn" style="opacity:.35;cursor:not-allowed">
        ⚙️&nbsp; Processing…
      </button>
    </div>`;
  document.getElementById('fhir-json').innerHTML = '<span style="color:var(--muted)">Building FHIR bundle…</span>';
  document.getElementById('valid-body').innerHTML = '<div style="color:var(--muted);font-size:11px">Running safety checks…</div>';
}}

function showFailedState(doc) {{
  _showDetail(); _loadDocImage(doc.id); switchTab('overview');
  document.getElementById('summary-panel').innerHTML = `
    <div class="state-card" style="border-color:var(--err)30">
      <div class="state-title" style="color:var(--err)">❌ Processing Failed</div>
      <div class="state-sub">${{esc(doc.error_message || 'An error occurred during pipeline execution. Check the activity log for details.')}}</div>
      <button onclick="processNow()" id="process-now-btn" class="process-btn">
        ↺&nbsp; Retry
      </button>
    </div>`;
  document.getElementById('fhir-json').innerHTML = '<span style="color:var(--muted)">No results — processing failed.</span>';
  document.getElementById('valid-body').innerHTML = '<div style="color:var(--muted);font-size:11px">No results — processing failed.</div>';
}}

// ── Process Now ───────────────────────────────────────────────────────────────
async function processNow() {{
  const btn = document.getElementById('process-now-btn');
  if (btn) {{ btn.disabled = true; btn.innerHTML = '⚙️&nbsp; Triggering…'; }}
  try {{
    const r = await fetch('/agent/process-now', {{method: 'POST'}});
    if (r.ok) {{
      if (btn) btn.innerHTML = '✔&nbsp; Triggered — watch activity feed';
      _lastPollTime = Date.now();
      if (_fastPollTimer) clearInterval(_fastPollTimer);
      _fastPollTimer = setInterval(() => {{ refreshAll(); refreshActivity(); }}, 2000);
      setTimeout(() => {{ if (_fastPollTimer) {{ clearInterval(_fastPollTimer); _fastPollTimer = null; }} }}, 60000);
    }} else {{
      if (btn) {{ btn.disabled = false; btn.innerHTML = '▶&nbsp; Process Now'; }}
    }}
  }} catch(e) {{
    if (btn) {{ btn.disabled = false; btn.innerHTML = '▶&nbsp; Process Now'; }}
  }}
}}

// ── Load results ─────────────────────────────────────────────────────────────
async function loadDocResults(id) {{
  _showDetail();
  _loadDocImage(id);
  const data = await fetchJ('/intake/' + id + '/results').catch(() => null);
  if (!data) return;
  renderSummary(data);
  renderFhir(data.fhir_bundle);
  renderValidation(data.validation, data.safety_flags);
  const val = data.validation || {{}};
  const ok  = val.overall_passed;
  const bc  = ok ? 'var(--accent)' : 'var(--warn)';
  document.getElementById('detail-badge').innerHTML =
    `<span class="status-pill" style="background:${{bc}}18;color:${{bc}};border:1px solid ${{bc}}35;padding:4px 12px;font-size:11px">
      ${{ok ? '✓ PASSED' : '⚠ REVIEW'}} ${{val.passed_count ?? 0}}/${{val.total_count ?? 0}}
    </span>`;
}}

// ── Summary ───────────────────────────────────────────────────────────────────
function renderSummary(data) {{
  const ex  = data.extraction_summary || {{}};
  const st  = data.standardization    || {{}};
  const icd = st.icd10 || {{}};
  const conf    = ex.overall_confidence;
  const confPct = conf != null ? (conf * 100).toFixed(0) + '%' : '—';
  const confColor = conf != null && conf > 0.8 ? 'var(--accent)' : 'var(--warn)';
  const flags   = ex.flags || [];
  const sfFlags = st.safety_flags || [];

  document.getElementById('summary-panel').innerHTML = `
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
        <div class="summ-card-val" style="color:var(--accent);font-family:'Fira Code',monospace">${{esc(icd.code||'—')}}</div>
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
        <div class="summ-card-val" style="color:${{confColor}};font-weight:700">${{confPct}}</div>
      </div>
      <div class="summ-card">
        <div class="summ-card-label">Doc ID</div>
        <div class="summ-card-val" style="font-family:'Fira Code',monospace;font-size:10px;color:var(--muted)">${{esc((data.document?.id||'').slice(0,8)+'…')}}</div>
      </div>
    </div>
    ${{flags.length ? `
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted);font-weight:600;margin-bottom:7px">Vision Flags</div>
      <div>${{flags.map(f=>`<span class="flag-tag">${{esc(String(f))}}</span>`).join('')}}</div>
    ` : ''}}
    ${{sfFlags.length ? `
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.7px;color:var(--warn);font-weight:600;margin:12px 0 7px">Clinical Flags</div>
      ${{sfFlags.map(f=>`
        <div style="background:#f59e0b10;border:1px solid #f59e0b25;border-radius:8px;
          padding:8px 10px;margin-bottom:5px">
          <span style="color:var(--warn);font-weight:700;font-size:10px">${{f.severity}}</span>
          <span style="color:var(--muted);margin-left:7px;font-size:11px">${{esc(f.description||'')}}</span>
        </div>
      `).join('')}}
    ` : ''}}
  `;
}}

// ── FHIR ──────────────────────────────────────────────────────────────────────
function renderFhir(bundle) {{
  _fhirData = bundle;
  if (!bundle) {{
    document.getElementById('fhir-json').innerHTML = '<span style="color:var(--muted)">No FHIR data</span>';
    return;
  }}
  document.getElementById('fhir-json').innerHTML = syntaxHL(JSON.stringify(bundle, null, 2));
}}

function syntaxHL(json) {{
  return json
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"([^"]+)":/g, (_,k) => `"<span class="jk">${{k}}</span>":`)
    .replace(/: "([^"]*)"([,\\n])/g, (_,v,end) => {{
      const cls = /^[A-Z]\d{{2}}/.test(v) ? 'jicd' : 'js';
      return `: "<span class="${{cls}}">${{v}}</span>"${{end}}`;
    }})
    .replace(/: (\d+\.?\d*)([,\\n ])/g, (_,v,end) => `: <span class="jn">${{v}}</span>${{end}}`)
    .replace(/: (true|false)/g, (_,v) => `: <span class="jb">${{v}}</span>`)
    .replace(/: (null)/g, `: <span class="jnull">null</span>`);
}}

function copyFhir() {{
  if (!_fhirData) return;
  navigator.clipboard.writeText(JSON.stringify(_fhirData, null, 2));
  const btn = document.querySelector('.copy-btn');
  btn.textContent = '✓ Copied!';
  setTimeout(() => btn.textContent = 'Copy JSON', 1800);
}}

// ── Validation ────────────────────────────────────────────────────────────────
function renderValidation(val, dbFlags) {{
  if (!val || !val.checks) {{
    document.getElementById('valid-body').innerHTML = '<div style="color:var(--muted);font-size:11px">No validation data</div>';
    return;
  }}
  const passed = val.passed_count, total = val.total_count;
  const pct = total ? Math.round((passed/total)*100) : 0;
  const summaryColor = val.overall_passed ? 'var(--accent)' : 'var(--err)';

  const doseCheck = val.checks.find(c => c.name === 'Dose Consistency' && !c.passed);
  const doseAlert = doseCheck ? `
    <div class="dose-alert">
      <div class="dose-alert-title">⚠ CRITICAL: Dose Variance Detected</div>
      <div class="dose-alert-body">${{esc(doseCheck.detail)}}</div>
    </div>` : '';

  const checksHtml = val.checks.map(c => `
    <div class="check-row ${{c.passed ? 'ok' : 'fail'}}">
      <div class="check-icon">${{c.passed ? '✅' : '❌'}}</div>
      <div>
        <div class="check-name" style="color:${{c.passed ? 'var(--accent)' : 'var(--err)'}}">${{esc(c.name)}}</div>
        <div class="check-det">${{esc(c.detail)}}</div>
      </div>
    </div>`).join('');

  const raisedHtml = dbFlags && dbFlags.length ? `
    <div style="font-size:9px;text-transform:uppercase;letter-spacing:.7px;color:var(--err);
      font-weight:600;margin:14px 0 8px">Raised Flags</div>
    ${{dbFlags.map(f => `
      <div class="raised-flag">
        <div class="raised-flag-type">${{f.severity}} · ${{f.flag_type}}</div>
        <div class="raised-flag-det">${{esc(f.details)}}</div>
        ${{f.resolved ? '<div style="color:var(--accent);font-size:9.5px;margin-top:4px">✓ Resolved</div>' : ''}}
      </div>
    `).join('')}}` : '';

  const summaryBar = `
    <div style="display:flex;align-items:center;gap:10px;padding:10px 12px;
      background:var(--card);border:1px solid var(--border);border-radius:9px;margin-bottom:12px">
      <div style="font-size:24px;font-weight:800;color:${{summaryColor}};
        font-variant-numeric:tabular-nums;line-height:1">${{passed}}/${{total}}</div>
      <div>
        <div style="font-size:11px;font-weight:600;color:${{summaryColor}}">
          ${{val.overall_passed ? '✓ All Checks Passed' : '⚠ Review Required'}}
        </div>
        <div style="font-size:10px;color:var(--muted);margin-top:2px">${{pct}}% compliance</div>
      </div>
    </div>`;

  document.getElementById('valid-body').innerHTML = summaryBar + doseAlert + checksHtml + raisedHtml;
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
  if (fail === 0) setUploadStatus('ok', '✓ ' + ok + ' doc' + (ok>1?'s':'') + ' queued — click Process Now or wait 30s');
  else setUploadStatus('err', ok + ' queued, ' + fail + ' failed');
  await refreshAll();
  if (lastId) selectDoc(lastId);
}}

async function runSimulate() {{
  const btn = document.getElementById('sim-btn');
  btn.disabled = true;
  setUploadStatus('loading', 'Injecting test batch…');
  try {{
    const r = await fetch('/intake/simulate');
    const d = await r.json();
    setUploadStatus('ok', '✓ ' + d.queued_count + ' docs injected — click Process Now or wait for auto-pickup');
    await refreshAll();
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
  const scroll = document.getElementById('act-scroll');
  const bar    = document.getElementById('act-active-bar');
  const status = document.getElementById('act-status');
  status.textContent = data.entries.length + ' events';
  if (data.has_active) {{
    bar.style.display = 'flex';
    const latest = data.entries.slice().reverse().find(e => e.event === 'stage_start');
    document.getElementById('act-active-msg').textContent =
      latest ? latest.message.replace('⏳ ','') : 'Processing…';
  }} else {{
    bar.style.display = 'none';
  }}
  if (!data.entries.length) {{
    scroll.innerHTML = '<div class="act-empty">Waiting for agent activity…</div>';
    return;
  }}
  const wasAtBottom = scroll.scrollHeight - scroll.scrollTop <= scroll.clientHeight + 40;
  scroll.innerHTML = data.entries.map(e => {{
    const lvl      = e.level || 'info';
    const stageTag = e.stage ? `<span class="act-stage">${{esc(e.stage)}}</span>` : '';
    return `<div class="act-row level-${{lvl}}">
      <span class="act-ts">${{fmtTime(e.timestamp)}}</span>
      <span class="act-msg">${{esc(e.message)}}</span>
      ${{stageTag}}
    </div>`;
  }}).join('');
  if (wasAtBottom) scroll.scrollTop = scroll.scrollHeight;
}}

// ── Uptime ────────────────────────────────────────────────────────────────────
function refreshUptime() {{
  if (!_startedAt) return;
  const s = Math.floor((Date.now() - _startedAt) / 1000);
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), sec = s%60;
  setText('kpi-uptime', h > 0 ? h+'h '+m+'m' : m > 0 ? m+'m '+sec+'s' : sec+'s');
}}

// ── Utils ─────────────────────────────────────────────────────────────────────
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


def _is_recent(ts: str, seconds: int) -> bool:
    try:
        dt  = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() < seconds
    except Exception:
        return False


def _format_uptime(started_at: str) -> str:
    try:
        dt    = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        total = int(delta.total_seconds())
        h, r  = divmod(total, 3600)
        m, s  = divmod(r, 60)
        if h > 0: return f"{h}h {m}m"
        if m > 0: return f"{m}m {s}s"
        return f"{s}s"
    except Exception:
        return "—"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
