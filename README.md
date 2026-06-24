# 🧬 MCRI Clinical Trial Management System (CTMS)

A MongoDB-backed Clinical Trial Management System for **Meridian Clinical Research
Institute (MCRI)**, replacing a spreadsheet-based workflow with a three-tier data
platform: **MongoDB → FastAPI → Streamlit**.

> **SECB3213** Bioinformatics Data Engineering Mini Project · Use Case 1

---

## 📋 What this is

The system stores **patients, trials, interventions, and adverse events** in
MongoDB, exposes them through a read-only REST API (10 analytical endpoints), and
surfaces them in an interactive portal so clinicians can browse trials, search
patients, monitor adverse events, and view analytics — without touching the
database.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│   MongoDB    │ ──▶ │   FastAPI    │ ──▶ │  Streamlit   │ ──▶ │  Browser │
│   (Atlas)    │     │  10 endpoints│     │  5 features  │     │  (user)  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────┘
  data layer            API layer          presentation         consumer
```

The portal **only** talks to the API over HTTP; it never queries MongoDB directly.

---

## 📂 Folder structure

```
BioDb_MiniProject/
├── D1_schemas/        # MongoDB $jsonSchema validators (4 collections)
├── D2_ingestion/      # pymongo ingestion script + source CSVs
├── D3_backup/         # mongodump archive of the populated database
├── D4_queries/        # 10 analytical aggregation pipelines (AR1–AR10)
├── D5_api/            # FastAPI app (app.py + queries.py)
├── D6_portal/         # Streamlit portal (portal.py)
├── D7_report/         # Technical report (PDF)
├── D8_video/          # Demonstration video
├── AI_Declaration/    # AI usage declaration + logs
└── README.md          # ← this file
```

---

## ✅ Prerequisites

| Need | Install |
|------|---------|
| Python 3.10+ | https://www.python.org/downloads/ |
| MongoDB Atlas account (or local MongoDB) | https://www.mongodb.com/atlas |
| MongoDB Database Tools (`mongodump` / `mongorestore`) | https://www.mongodb.com/try/download/database-tools |
| Python packages | `pip install pymongo fastapi "uvicorn[standard]" streamlit requests pandas` |

> Set your connection string once per terminal session (PowerShell):
> ```powershell
> $env:MONGO_URI="mongodb+srv://<user>:<password>@<cluster>/"
> $env:MONGO_DB="ctms"
> ```
> macOS/Linux: use `export MONGO_URI="..."` instead.

---

## 🚀 Setup & run

There are two ways to get the database populated: **restore the backup** (fastest)
or **run the ingestion from the CSVs**. Do one of them, then start the API and the
portal.

### Option A — Restore the backup (D3)  ·  fastest

```bash
mongorestore --uri "mongodb+srv://<user>:<password>@<cluster>/" D3_backup/dump
```
This recreates the `ctms` database with all four collections
(100 patients, 10 trials, 20 interventions, 300 adverse events).

### Option B — Ingest from the CSVs (D1 + D2)

```bash
cd D2_ingestion
python ingest.py --mongo "mongodb+srv://<user>:<password>@<cluster>/" \
                 --db ctms --csv-dir ./data --schema-dir ../D1_schemas
```
Expected output:
```
Referential consistency OK: all foreign IDs resolve.
Ingestion complete. Document counts:
  patients           100
  trials              10
  interventions       20
  adverse_events     300
```

---

### Step 2 — Start the API (D5)  ·  Terminal 1

```bash
cd D5_api
$env:MONGO_URI="mongodb+srv://<user>:<password>@<cluster>/"
uvicorn app:app --reload
```
- Interactive API docs (Swagger UI): **http://127.0.0.1:8000/docs**
- Leave this terminal running — it is the server.
- If `uvicorn` isn't recognised: `python -m uvicorn app:app --reload`

### Step 3 — Launch the portal (D6)  ·  Terminal 2

```bash
cd D6_portal
streamlit run portal.py
```
Opens automatically at **http://localhost:8501**.

> ⚠️ **Order matters.** Start the API *first*, then the portal. The portal calls
> the API — if the API is down it shows "Cannot reach the API".
> If your API runs on a different host/port, set `API_BASE` before launching:
> `$env:API_BASE="http://127.0.0.1:8000"`.

---

## 🔌 API endpoints (D4 + D5)

Read-only, lowercase-hyphenated URLs, response envelope `{ total, page, limit, data }`.

| AR | Endpoint |
|----|----------|
| AR1 | `GET /api/trials` |
| AR2 | `GET /api/trials/{trial_id}/patients` |
| AR3 | `GET /api/patients` |
| AR4 | `GET /api/patients/{patient_id}/adverse-events` |
| AR5 | `GET /api/analytics/ae-by-intervention-type` |
| AR6 | `GET /api/analytics/enrolment-progress` |
| AR7 | `GET /api/trials/{trial_id}/safety-matrix` |
| AR8 | `GET /api/analytics/comorbidity-ae-burden` |
| AR9 | `GET /api/interventions` |
| AR10 | `GET /api/analytics/ae-trend` |

**Quick test** (with the API running, paste into a browser):
```
http://127.0.0.1:8000/api/trials?status=Recruiting
http://127.0.0.1:8000/api/patients/PT-000028/adverse-events?min_grade=3
http://127.0.0.1:8000/api/interventions?gene=EGFR
```

---

## 🖥️ Portal features (D6)

| # | Feature | API used |
|---|---------|----------|
| 1 | Trial Browser (status / phase / sponsor filters) | AR1 |
| 2 | Patient Search (all patients, or within a trial) | AR3 / AR2 |
| 3 | AE Monitor (colour-coded by CTCAE grade) | AR4 |
| 4 | Analytics (charts update on filter change) | AR5 / AR6 / AR10 |
| 5 | Enrolment & Explorer (safety matrix, comorbidity, target search) | AR7 / AR8 / AR9 |

Severity scale: 🟢 1 Mild · 🟩 2 Moderate · 🟠 3 Severe · 🔴 4 Life-threatening · 🟥 5 Fatal

---

## 💾 Create a fresh backup

```bash
mongodump --uri "mongodb+srv://<user>:<password>@<cluster>/ctms" --out D3_backup/dump
```

---

## 🧩 Troubleshooting

| Symptom | Fix |
|---------|-----|
| `'mongodump' / 'uvicorn' not recognized` | Tool not on PATH — use the full path, or `python -m uvicorn ...` |
| `No module named 'queries'` | `queries.py` must be in the same folder as `app.py` (D5_api) |
| Portal: "Cannot reach the API" | Start the API first; confirm it's at `127.0.0.1:8000` |
| Atlas connection times out | Cluster is paused (resume it) or your IP isn't allowlisted (Atlas → Network Access → add IP / `0.0.0.0/0`) |
| Endpoints return empty `data` | Database not populated — run Option A or B first; check `--db ctms` |

---

## 🛠️ Tech stack

MongoDB Atlas · Python · pymongo · FastAPI · Uvicorn · Streamlit · pandas · MongoDB Database Tools

---

## 👥 Team

| Member | Owns |
|--------|------|
| _[Name A]_ | Database layer — schema, ingestion, backup |
| _[Name B]_ | API / query layer — 10 ARs, FastAPI |
| _[Name C]_ | Portal, integration, video, packaging |