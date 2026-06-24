# D6 — Data Portal

A read-only **Streamlit** web portal for the MCRI Clinical Trial Management System (CTMS).
It is built for clinicians, investigators, and analysts who need to explore trial,
patient, and adverse-event data through a point-and-click interface.

The portal consumes the **D5 FastAPI** endpoints over HTTP only — it **never** connects to
MongoDB directly. This keeps all business logic and data access in the API layer (D5),
with D6 acting purely as a presentation client.

```
┌──────────┐   HTTP/JSON   ┌──────────┐   driver   ┌──────────┐
│  D6      │ ────────────► │  D5      │ ─────────► │ MongoDB  │
│  Portal  │ ◄──────────── │  FastAPI │ ◄───────── │          │
│ (Streamlit)              │  (API)   │            │          │
└──────────┘               └──────────┘            └──────────┘
```

## Features

The portal exposes five features in the sidebar, each backed by one or more API
endpoints and each with at least one interactive filter.

| # | Feature | API requirement(s) | Endpoint(s) | Highlights |
|---|---------|--------------------|-------------|------------|
| 1 | **Trial Browser** | AR1 | `/api/trials` | Filter trials by status, phase, or sponsor |
| 2 | **Patient Search** | AR3, AR2 | `/api/patients`, `/api/trials/{id}/patients` | Search across all patients or within one trial |
| 3 | **AE Monitor** | AR4 | `/api/patients/{id}/adverse-events` | Per-patient adverse-event history, colour-coded by CTCAE grade |
| 4 | **Analytics** | AR5, AR6, AR10 | `/api/analytics/ae-by-intervention-type`, `/enrolment-progress`, `/ae-trend` | Charts that update live on filter changes |
| 5 | **Enrolment & Explorer** | AR7, AR8, AR9 | `/api/trials/{id}/safety-matrix`, `/api/analytics/comorbidity-ae-burden`, `/api/interventions` | Safety matrix, comorbidity burden, molecular-target explorer |

### Feature detail

1. **Trial Browser** — Lists clinical trials with selectbox filters for status, phase, and
   sponsor. Filter option lists are pulled live from the data (not hardcoded).
2. **Patient Search** — Two modes:
   - *Across all patients (AR3)*: filter by gender, ethnicity, site, smoking status, and ICD-10 diagnosis code.
   - *Within one trial (AR2)*: pick a trial, then filter its patients by gender / smoking status.
3. **AE Monitor** — Enter a patient ID to pull their full adverse-event history. Rows are
   colour-coded by CTCAE grade (🟢 1 Mild → 🟥 5 Fatal). Filter by minimum grade and seriousness.
4. **Analytics** — Three tabs:
   - AE counts by intervention type (toggle total / serious / proportion).
   - Enrolment-progress completion %, filterable by sponsor and phase.
   - Monthly AE trend line chart, filterable by trial and intervention type.
5. **Enrolment & Explorer** — Three tabs:
   - *Safety matrix (AR7)*: causality × CTCAE-grade cross-tab for a chosen trial.
   - *Comorbidity burden (AR8)*: patients above a comorbidity threshold with their AE burden.
   - *Target explorer (AR9)*: find interventions by molecular target gene / protein.

## Requirements

- Python 3.8+
- The **D5 API** running and reachable (see `../D5_Api`)

## Installation

```bash
pip install streamlit requests pandas
```

## Running

1. **Start the D5 API first** (from the `D5_Api` directory):

   ```bash
   uvicorn app:app --reload
   ```

   This serves the API at `http://127.0.0.1:8000` by default.

2. **Launch the portal:**

   ```bash
   streamlit run portal.py
   ```

   Streamlit opens the portal in your browser (typically `http://localhost:8501`).

## Configuration

The API base URL is read from the `API_BASE` environment variable, defaulting to
`http://127.0.0.1:8000`. Point the portal at a different API host like so:

```bash
# PowerShell
$env:API_BASE = "http://my-api-host:8000"; streamlit run portal.py

# bash
API_BASE=http://my-api-host:8000 streamlit run portal.py
```

The current API address is shown in the sidebar caption.

## Implementation notes

- **Caching** — API responses are cached with `@st.cache_data` (60 s TTL; 300 s for filter
  option lists) to keep the UI responsive and reduce load on D5.
- **Error handling** — `api_get()` cleanly handles a down API (connection error → friendly
  message and stop), `404`/`422` (returned as empty results with an inline warning), and
  `5xx` (surfaced as a server error).
- **No hardcoded options** — filter dropdowns for status, phase, sponsor, and trial IDs are
  derived from live data, so the portal generalises to any dataset served by D5.

## Project context

This is component **D6** of the MCRI CTMS mini-project. Related components:

| Component | Purpose |
|-----------|---------|
| D1_Schemas | Data model / schema definitions |
| D2_ingestion | Data ingestion pipeline |
| D3_backup | Database backup |
| D4_Queries,Results | Query development and results |
| **D5_Api** | **FastAPI service this portal consumes** |
| **D6_Portal** | **This Streamlit portal** |
