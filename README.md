# 🧬 BioVault Agent

> **Autonomous clinical document watchdog running on [Akash Network](https://akash.network)**

BioVault Agent continuously monitors an intake queue, processes handwritten chemotherapy charts through a 4-stage AI pipeline, detects critical safety anomalies (dose drops, drug name errors), and autonomously escalates alerts — all inside a single Docker container deployed on decentralized infrastructure.

---

## What it does

A judge visits the live Akash URL. They see a dashboard with the agent heartbeat ticking. They hit `/intake/simulate` to inject 5 test documents. The dashboard updates in real time as the agent processes each one, catches the Daunorubicin dose drop (90mg → 80mg, 11% variance), raises a `CRITICAL` alert, POSTs to the webhook, and logs the autonomous action. The state persists across refreshes.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Single Docker Container (Akash Network)                 │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  FastAPI (uvicorn, port 8000)                       │ │
│  │    GET  /dashboard   — live judge demo screen       │ │
│  │    GET  /health      — agent status + heartbeat     │ │
│  │    POST /intake      — upload document to queue     │ │
│  │    GET  /intake/simulate — inject test batch        │ │
│  │    GET  /alerts      — unresolved safety flags      │ │
│  └──────────────────────────┬──────────────────────────┘ │
│                             │ lifespan starts             │
│  ┌──────────────────────────▼──────────────────────────┐ │
│  │  Agent Daemon Thread (polls every 30s)              │ │
│  │    1. MiniMax Vision  — extract from image          │ │
│  │    2. AkashML LLM     — standardize + ICD-10        │ │
│  │    3. FHIR R4 Builder — build bundle                │ │
│  │    4. Safety Validator — 5 deterministic checks     │ │
│  │    5. Alert Dispatch   — webhook + structured log   │ │
│  └──────────────────────────┬──────────────────────────┘ │
│                             │                             │
│  ┌──────────────────────────▼──────────────────────────┐ │
│  │  SQLite (/data/biovault.db)                         │ │
│  │    documents · pipeline_results                     │ │
│  │    safety_flags · agent_heartbeat                   │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## Hackathon requirements satisfied

| Requirement | How |
|---|---|
| Autonomous agent, continuously operating | Daemon thread polls queue every 30s indefinitely |
| Verifiable real-world actions | API calls (MiniMax, AkashML), webhook POSTs, DB writes |
| Persistent state | SQLite at `/data/biovault.db` survives container restarts |
| Runs on Akash | `deploy.yaml` SDL, single-container, port 8000 |
| Uses AkashML for inference | `pipeline/akash_agent.py` → `chatapi.akash.network` |
| Fault tolerance | Startup recovers `processing` → `pending` on restart |

---

## Quickstart (local)

```bash
# 1. Clone and enter the repo
cd biovault-agent

# 2. Configure environment
cp .env.example .env
# Edit .env: add MINIMAX_API_KEY and AKASH_API_KEY

# 3. Create virtual environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 4. Run
uvicorn main:app --reload --port 8000

# 5. Open the dashboard
open http://localhost:8000/dashboard

# 6. Inject test documents
curl http://localhost:8000/intake/simulate
```

---

## Docker

```bash
# Build
docker build -t biovault-agent:latest .

# Run (with persistent volume)
docker run -p 8000:8000 \
  -v biovault-data:/data \
  -e MINIMAX_API_KEY=your_key \
  -e AKASH_API_KEY=your_key \
  biovault-agent:latest
```

---

## Deploy to Akash

```bash
# 1. Push image to Docker Hub
docker build -t yourname/biovault-agent:latest .
docker push yourname/biovault-agent:latest

# 2. Edit deploy.yaml — replace image name and add API keys to env section

# 3. Deploy
akash tx deployment create deploy.yaml --from your-wallet

# 4. Accept a bid and get the URL
akash provider lease-status --from your-wallet ...
```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Agent status, heartbeat, uptime |
| `/dashboard` | GET | Live HTML judge demo screen |
| `/intake` | POST | Upload document (multipart image) |
| `/intake/simulate` | GET | Inject 5 test documents |
| `/intake/queue` | GET | Queue stats |
| `/alerts` | GET | Unresolved safety flags |
| `/alerts/all` | GET | All flags (last 50) |
| `/alerts/resolve/{id}` | POST | Resolve a flag |
| `/docs` | GET | Interactive API docs (Swagger) |

---

## Pipeline stages

1. **MiniMax Vision** (`MiniMax-Text-01`) — base64 image → structured JSON extraction with per-field confidence scores. **Not modified from original BioVault.**

2. **AkashML Standardization** (`Meta-Llama-3-1-8B-Instruct-FP8`) — maps ICD-10, normalizes drug names, detects dose variance. **Replaced AWS Bedrock + MiniMax-M2.5 fallback.**

3. **FHIR R4 Builder** — constructs HL7-compliant Bundle with de-identified patient. **Not modified.**

4. **Safety Validator** — 5 deterministic Python checks: PII, ICD-10 validity, dose consistency, FHIR schema, drug name standardization. **Not modified.**

---

## Project structure

```
biovault-agent/
  pipeline/
    __init__.py
    minimax_agent.py    ← original, untouched
    akash_agent.py      ← AkashML replacement for bedrock_agent
    validator.py        ← original, untouched
    fhir_builder.py     ← original, import path updated
    datadog_tracer.py   ← original, untouched
    demo_chart.jpeg     ← real Delta Hospital AML chart
  agent.py              ← autonomous daemon loop
  database.py           ← SQLite schema + all helpers
  intake.py             ← document upload + simulate endpoints
  alerts.py             ← safety flag endpoints + webhook dispatch
  dashboard.py          ← live HTML dashboard
  main.py               ← FastAPI app + lifespan + /health
  Dockerfile
  deploy.yaml           ← Akash SDL
  startup.sh
  requirements.txt
  .env.example
```

---

*Built for the Akash Agent Track hackathon. Patient data in demo is real but de-identified in all outputs.*
