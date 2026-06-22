# 🧬 MCRI Clinical Trial Management System (CTMS)

> A MongoDB-backed Clinical Trial Management System for Meridian Clinical Research
> Institute (MCRI), replacing an ageing spreadsheet-based workflow with a proper
> three-tier data platform: **MongoDB → FastAPI → Streamlit**.

![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-47A248?logo=mongodb&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-REST_API-009688?logo=fastapi&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Portal-FF4B4B?logo=streamlit&logoColor=white)
![Status](https://img.shields.io/badge/status-D1→D6_complete-success)

---

## 📖 What this project does

MCRI runs oncology and infectious-disease clinical trials across five research
sites. This system stores **patients, trials, interventions, and adverse events**
in MongoDB and exposes them through a read-only REST API and an interactive portal
so clinicians — not just data engineers — can browse trials, search patients,
monitor adverse events, and view analytics, all without touching the database.

---

## 🏗️ Architecture

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────┐
│   MongoDB    │ ───▶ │   FastAPI    │ ───▶ │  Streamlit   │ ───▶ │  Browser │
│   (Atlas)    │      │   REST API   │      │    Portal    │      │  (user)  │
│  4 colls     │      │ 10 endpoints │      │  5 features  │      │          │
│   D1 · D2    │      │   D4 · D5    │      │     D6       │      │          │
└──────────────┘      └──────────────┘      └──────────────┘      └──────────┘
   data layer            API layer            presentation         consumer

Data flows ONE direction. The portal never touches MongoDB directly — it only
calls the API over HTTP.
```

---

## 📂 Repository structure

```
BioDb_MiniProject/
├── D1_schemas/        # MongoDB $jsonSchema validators (4 collections)
├── D2_ingestion/      # pymongo script: CSV → nested validated documents
├── D3_backup/         # mongodump archive of the populated database
├── D4_queries/        # 10 analytical aggregation pipelines (AR1–AR10)
├── D5_api/            # FastAPI app exposing the 10 ARs as REST endpoints
├── D6_portal/         # Streamlit read-only portal (5 features)
├── D7_report/         # Technical report (PDF)
├── D8_video/          # Demonstration video
└── README.md          # ← you are here
```

---

## 🗂️ The four collections (D1)

| Collection | What it holds | Key relationships |
|------------|---------------|-------------------|
| `patients` | De-identified participants | references trials via `enrolled_trials[]` |
| `trials` | Trial protocols | embeds `arms[]`; references interventions |
| `interventions` | Treatments per arm | references one trial + one arm |
| `adverse_events` | AEs during trials | references patient + trial + intervention (all 3 mandatory) |

<details>
<summary><b>📐 Embed vs reference — the design decisions</b></summary>

- **Arms are embedded in trials** — an arm has no identity outside its trial and
  is always read with the protocol.
- **Patient ↔ trial is many-to-many, stored once** on the patient side
  (`enrolled_trials[]`). This fixes the duplication the old spreadsheet system had.
- **Adverse events carry three mandatory references** (patient, trial,
  intervention) and deliberately **do not** store the arm. To find an AE's arm you
  go AE → intervention → `arm_label`. That indirection is intentional.
- **Embedded objects** (read with their parent, no independent identity):
  `diagnosis`, `contact_info`, `dosage`, `lab_values`, `ethical_approval`, `arms`.

</details>

---

## 🚀 Quick start

> **Prerequisites:** Python 3.10+, a MongoDB Atlas cluster (or local MongoDB),
> and the MongoDB Database Tools (for the backup).

### Step 1 — Set up the database (D1 + D2)

```bash
cd D2_ingestion
pip install pymongo
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

### Step 2 — Start the API (D5)  ·  *Terminal 1*

```bash
cd D5_api
pip install fastapi "uvicorn[standard]" pymongo
# PowerShell:
$env:MONGO_URI="mongodb+srv://<user>:<password>@<cluster>/"
uvicorn app:app --reload
```
Then open the interactive API docs: **http://127.0.0.1:8000/docs**

### Step 3 — Launch the portal (D6)  ·  *Terminal 2*

```bash
cd D6_portal
pip install streamlit requests pandas
streamlit run portal.py
```
Opens automatically at **http://localhost:8501**

> ⚠️ **The API and portal run together.** Start the API *first* (Step 2), then the
> portal (Step 3). The portal calls the API — if the API is down, the portal shows
> "Cannot reach the API".

---

## 🔌 The 10 API endpoints (D4 + D5)

All endpoints are **GET only** (read-only), lowercase-hyphenated, with the response
envelope `{ total, page, limit, data: [...] }`.

| AR | Endpoint | Purpose |
|----|----------|---------|
| AR1 | `GET /api/trials` | Filter trials by status / phase / sponsor |
| AR2 | `GET /api/trials/{trial_id}/patients` | Patients enrolled in a trial |
| AR3 | `GET /api/patients` | Search patients by demographics / diagnosis |
| AR4 | `GET /api/patients/{patient_id}/adverse-events` | A patient's full AE history |
| AR5 | `GET /api/analytics/ae-by-intervention-type` | AE counts + % serious per type |
| AR6 | `GET /api/analytics/enrolment-progress` | Enrolment % vs target per trial |
| AR7 | `GET /api/trials/{trial_id}/safety-matrix` | Causality × grade cross-tab |
| AR8 | `GET /api/analytics/comorbidity-ae-burden` | High-comorbidity patients + AE load |
| AR9 | `GET /api/interventions` | Interventions by gene / protein target |
| AR10 | `GET /api/analytics/ae-trend` | Monthly AE time-series |

<details>
<summary><b>💡 Try a few in the browser</b></summary>

With the API running, paste these into your browser:

```
http://127.0.0.1:8000/api/trials?status=Recruiting
http://127.0.0.1:8000/api/patients?gender=Female&smoking_status=Never
http://127.0.0.1:8000/api/patients/PT-000028/adverse-events?min_grade=3
http://127.0.0.1:8000/api/analytics/ae-by-intervention-type
http://127.0.0.1:8000/api/interventions?gene=EGFR
```

</details>

---

## 🖥️ The portal's 5 features (D6)

| # | Feature | Calls | What you can do |
|---|---------|-------|-----------------|
| 1 | **Trial Browser** | AR1 | Filter trials by status, phase, sponsor |
| 2 | **Patient Search** | AR3 / AR2 | Search all patients, or within one trial |
| 3 | **AE Monitor** | AR4 | A patient's AEs, **colour-coded by severity** 🟢🟠🔴 |
| 4 | **Analytics** | AR5 / AR6 / AR10 | Charts that redraw on filter change |
| 5 | **Enrolment & Explorer** | AR7 / AR8 / AR9 | Safety matrix, comorbidity burden, target search |

**Severity colour scale (CTCAE grade):**
🟢 1 Mild · 🟩 2 Moderate · 🟠 3 Severe · 🔴 4 Life-threatening · 🟥 5 Fatal

---

## 💾 Restoring the backup (D3)

To restore the database dump into any MongoDB:

```bash
mongorestore --uri "mongodb+srv://<user>:<password>@<cluster>/" D3_backup/dump
```

To create a fresh backup:

```bash
mongodump --uri "mongodb+srv://<user>:<password>@<cluster>/ctms" --out D3_backup/dump
```

---

## 🛠️ Tech stack

| Layer | Technology |
|-------|-----------|
| Database | MongoDB Atlas (M0), `$jsonSchema` validation |
| Ingestion | Python, `pymongo` |
| API | FastAPI, Uvicorn |
| Portal | Streamlit, `requests`, `pandas` |
| Backup | MongoDB Database Tools (`mongodump` / `mongorestore`) |

---

## 🧩 Troubleshooting

<details>
<summary><b>Common issues and fixes</b></summary>

| Symptom | Cause / fix |
|---------|-------------|
| `'mongodump' / 'uvicorn' not recognized` | Tool not on PATH. Use full path, or `python -m uvicorn ...` |
| `No module named 'queries'` | `queries.py` must sit next to `app.py` in `D5_api/` |
| Portal: "Cannot reach the API" | Start the API first; check it's on `127.0.0.1:8000` |
| Atlas connection fails / times out | Cluster paused (resume it) or your IP isn't allowlisted (Network Access → add IP / `0.0.0.0/0`) |
| Endpoints return empty `data` | DB not ingested — run D2 first, check `--db ctms` |
| Schema rejects a document on ingest | A field violates the validator — the message names the field |

</details>

---

## 📑 Deliverables map

| ID | Deliverable | Location |
|----|-------------|----------|
| D1 | Schema design (`$jsonSchema`) | `D1_schemas/` |
| D2 | Ingestion script + counts | `D2_ingestion/` |
| D3 | Database backup | `D3_backup/` |
| D4 | 10 queries + results | `D4_queries/` |
| D5 | FastAPI implementation | `D5_api/` |
| D6 | Streamlit portal | `D6_portal/` |
| D7 | Technical report | `D7_report/` | OTW
| D8 | Demonstration video | `D8_video/` | OTW

---

<p align="center"><i>Built for SECB3213 · Bioinformatics Data Engineering Mini Project</i></p>
