# D5 — FastAPI Implementation (CTMS API)

This is the read-only REST API for the MCRI Clinical Trial Management System.
It exposes all 10 analytical requirements (AR1–AR10) as HTTP endpoints. The
portal (D6) calls these endpoints — it never touches MongoDB directly.

---

## What's in this folder

| File | What it is |
|------|-----------|
| `app.py` | The FastAPI app. Defines all 10 endpoints. **This is the D5 deliverable.** |
| `queries.py` | The MongoDB aggregation pipelines (same file as D4). `app.py` imports these. |

**Both files must stay together.** `app.py` does `import queries`, so if
`queries.py` is missing the server won't start (`No module named 'queries'`).
The query logic lives in one place so D4 and D5 share it.

---

## How to run it

### 1. Install dependencies (one time)
```
pip install fastapi "uvicorn[standard]" pymongo
```

### 2. Set the MongoDB connection string
The API reads the connection from an environment variable so the password isn't
hardcoded. In PowerShell:
```
$env:MONGO_URI="mongodb+srv://<user>:<password>@cluster0.vbpqafo.mongodb.net/"
$env:MONGO_DB="ctms"
```
(Defaults if unset: `mongodb://localhost:27017` and database `ctms`.)

### 3. Start the server
```
uvicorn app:app --reload
```
`app:app` = "in file app.py, use the variable named app".
If `uvicorn` isn't recognised, use: `python -m uvicorn app:app --reload`.

You should see `Application startup complete.` and the server stays running.
Leave this terminal open — it IS the server. Press Ctrl+C to stop.

### 4. Open the interactive docs
In a browser, go to:
```
http://127.0.0.1:8000/docs
```
This is the Swagger UI. Every endpoint has a "Try it out" button — pick one,
fill in parameters, click Execute, and you get live JSON back. This page is what
we screen-record for the D8 video (segment 2).

---

## The 10 endpoints

All URLs are lowercase + hyphenated, use plural nouns, and are GET-only
(read-only API). Required IDs go in the path; optional filters go in the query
string.

| AR | Endpoint | Example |
|----|----------|---------|
| AR1 | `GET /api/trials` | `/api/trials?status=Recruiting&phase=Phase II` |
| AR2 | `GET /api/trials/{trial_id}/patients` | `/api/trials/NCT-20240001/patients?gender=Female` |
| AR3 | `GET /api/patients` | `/api/patients?ethnicity=Malay&site_id=SITE-05` |
| AR4 | `GET /api/patients/{patient_id}/adverse-events` | `/api/patients/PT-000028/adverse-events?min_grade=3` |
| AR5 | `GET /api/analytics/ae-by-intervention-type` | (no params) |
| AR6 | `GET /api/analytics/enrolment-progress` | `/api/analytics/enrolment-progress?status=Recruiting` |
| AR7 | `GET /api/trials/{trial_id}/safety-matrix` | `/api/trials/NCT-20240001/safety-matrix` |
| AR8 | `GET /api/analytics/comorbidity-ae-burden` | `/api/analytics/comorbidity-ae-burden?min_comorbidities=4` |
| AR9 | `GET /api/interventions` | `/api/interventions?gene=EGFR` |
| AR10 | `GET /api/analytics/ae-trend` | `/api/analytics/ae-trend?intervention_type=Drug` |

Plus `GET /` — a simple health check that returns service info.

---

## How a response looks

Every list endpoint returns the same envelope:
```json
{
  "total": 3,
  "page": 1,
  "limit": 20,
  "data": [ { ...row... }, { ...row... }, { ...row... } ]
}
```
- `total` — number of rows returned
- `page`, `limit` — pagination (where the endpoint supports it)
- `data` — the actual results

---

## Design notes (for the report / understanding)

- **Path vs query params.** Required resource IDs (a trial, a patient) are path
  parameters: `/api/trials/{trial_id}/patients`. Everything optional (filters,
  pagination) is a query parameter: `?gender=Female&page=1`.
- **URL grouping.** Resource collections are plural nouns (`/api/trials`,
  `/api/patients`, `/api/interventions`). Things that belong to a parent nest
  under it (`/api/trials/{id}/patients`). Cross-cutting aggregations live under
  `/api/analytics/...`.
- **Generalised, not hardcoded.** Each endpoint passes its parameters into the
  matching pipeline function in `queries.py`. Absent filters are simply not
  applied, so one endpoint covers many filter combinations.
- **Error handling.**
  - `404` — the trial or patient ID doesn't exist.
  - `422` — invalid input (e.g. AR9 called with no gene AND no protein, or
    `min_grade` outside 1–5). FastAPI also auto-returns 422 for wrong types.
  - `500` — a database error.

---

## Common problems

| Symptom | Cause / fix |
|---------|-------------|
| `No module named 'queries'` | `queries.py` isn't in the same folder as `app.py`. |
| `'uvicorn' is not recognized` | Use `python -m uvicorn app:app --reload`. |
| Browser: "connection refused" | The server stopped. Restart with `uvicorn app:app --reload`. |
| Endpoints return empty `data` | `MONGO_URI` / `MONGO_DB` point at the wrong place, or the DB isn't ingested (run D2 first). |
| Atlas connection fails | Cluster is paused (resume it in Atlas) or your IP isn't allowlisted (Network Access → add IP). |

---

## How D5 connects to the rest

```
MongoDB (ctms)  ──>  queries.py (pipelines)  ──>  app.py (FastAPI)  ──>  D6 portal
   (D2 loaded)          (D4)                        (D5, this)            (next)
```
The portal in D6 will send HTTP requests to these endpoints and display the
results as tables and charts — so non-technical users never see Swagger or the
database.