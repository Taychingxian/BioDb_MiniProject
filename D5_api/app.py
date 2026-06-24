#!/usr/bin/env python3
"""
D5 - FastAPI implementation for the MCRI CTMS.

Exposes all 10 analytical requirements (AR1-AR10) as a read-only REST API.
Each endpoint generalises the corresponding D4 pipeline by accepting parameters
rather than hardcoded values. The pipeline logic lives in queries.py and is
imported here, so there is a single source of truth.

Conventions followed (brief Section 5 / D5):
  - URLs: lowercase, hyphen-separated  (e.g. /api/adverse-events)
  - Resource naming: plural nouns      (/api/trials, /api/patients)
  - Path params for required IDs        (/api/trials/{trial_id}/patients)
  - Query params for optional filters + pagination
  - GET only (read-only)
  - List envelope: { total, page, limit, data: [...] }
  - HTTPException with 404 / 422 / 500
  - Swagger UI available at /docs

Run:
    pip install fastapi "uvicorn[standard]" pymongo
    set MONGO_URI=mongodb+srv://USER:PASS@cluster0.xxxx.mongodb.net/   (Windows)
    uvicorn app:app --reload
Then open http://127.0.0.1:8000/docs
"""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Path, Query
from pymongo import MongoClient
from pymongo.errors import PyMongoError

import queries as q   # the 10 AR pipeline functions from D4

# ---------------------------------------------------------------------------
# database connection (read once at startup)
# ---------------------------------------------------------------------------
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGO_DB", "ctms")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

app = FastAPI(
    title="MCRI CTMS API",
    version="1.0.0",
    description="Read-only analytical API over the Clinical Trial Management System. "
                "Implements AR1-AR10.",
)


def envelope(data, page=1, limit=None):
    """Standard list response envelope required by the brief."""
    return {
        "total": len(data),
        "page": page,
        "limit": limit if limit is not None else len(data),
        "data": data,
    }


def run(fn, *args, **kwargs):
    """Execute a pipeline function, translating DB errors into HTTP 500."""
    try:
        return fn(db, *args, **kwargs)
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")


# ===========================================================================
# AR1 - GET /api/trials  (filter by status / phase / sponsor)
# ===========================================================================
@app.get("/api/trials", tags=["Trials"])
def list_trials(
    status: Optional[str] = Query(None, description="e.g. Recruiting, Completed"),
    phase: Optional[str] = Query(None, description="e.g. Phase II"),
    sponsor: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    data = run(q.ar1_filter_trials, status=status, phase=phase,
               sponsor=sponsor, page=page, limit=limit)
    return envelope(data, page=page, limit=limit)


# ===========================================================================
# AR2 - GET /api/trials/{trial_id}/patients
# ===========================================================================
@app.get("/api/trials/{trial_id}/patients", tags=["Trials"])
def patients_in_trial(
    trial_id: str = Path(..., description="e.g. NCT-20240001"),
    gender: Optional[str] = Query(None),
    smoking_status: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    # 404 if the trial itself does not exist
    if db.trials.count_documents({"trial_id": trial_id}, limit=1) == 0:
        raise HTTPException(status_code=404, detail=f"Trial {trial_id} not found")
    data = run(q.ar2_patients_in_trial, trial_id, gender=gender,
               smoking_status=smoking_status, site_id=site_id,
               page=page, limit=limit)
    return envelope(data, page=page, limit=limit)


# ===========================================================================
# AR3 - GET /api/patients  (search by demographic / clinical criteria)
# ===========================================================================
@app.get("/api/patients", tags=["Patients"])
def search_patients(
    gender: Optional[str] = Query(None),
    ethnicity: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    smoking_status: Optional[str] = Query(None),
    diagnosis_code: Optional[str] = Query(None, description="ICD-10, e.g. C34.1"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    data = run(q.ar3_search_patients, gender=gender, ethnicity=ethnicity,
               site_id=site_id, smoking_status=smoking_status,
               diagnosis_code=diagnosis_code, page=page, limit=limit)
    return envelope(data, page=page, limit=limit)


# ===========================================================================
# AR4 - GET /api/patients/{patient_id}/adverse-events
# ===========================================================================
@app.get("/api/patients/{patient_id}/adverse-events", tags=["Patients"])
def patient_adverse_events(
    patient_id: str = Path(..., description="e.g. PT-000028"),
    min_grade: Optional[int] = Query(None, ge=1, le=5),
    serious: Optional[bool] = Query(None),
    intervention_id: Optional[str] = Query(None),
):
    if db.patients.count_documents({"patient_id": patient_id}, limit=1) == 0:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    data = run(q.ar4_patient_ae_history, patient_id, min_grade=min_grade,
               serious=serious, intervention_id=intervention_id)
    return envelope(data)


# ===========================================================================
# AR5 - GET /api/analytics/ae-by-intervention-type
# ===========================================================================
@app.get("/api/analytics/ae-by-intervention-type", tags=["Analytics"])
def ae_by_intervention_type():
    data = run(q.ar5_ae_by_intervention_type)
    return envelope(data)


# ===========================================================================
# AR6 - GET /api/analytics/enrolment-progress
# ===========================================================================
@app.get("/api/analytics/enrolment-progress", tags=["Analytics"])
def enrolment_progress(
    sponsor: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    data = run(q.ar6_enrolment_progress, sponsor=sponsor, phase=phase, status=status)
    return envelope(data)


# ===========================================================================
# AR7 - GET /api/trials/{trial_id}/safety-matrix
# ===========================================================================
@app.get("/api/trials/{trial_id}/safety-matrix", tags=["Trials"])
def safety_matrix(trial_id: str = Path(..., description="e.g. NCT-20240001")):
    if db.trials.count_documents({"trial_id": trial_id}, limit=1) == 0:
        raise HTTPException(status_code=404, detail=f"Trial {trial_id} not found")
    data = run(q.ar7_causality_severity_matrix, trial_id)
    return envelope(data)


# ===========================================================================
# AR8 - GET /api/analytics/comorbidity-ae-burden
# ===========================================================================
@app.get("/api/analytics/comorbidity-ae-burden", tags=["Analytics"])
def comorbidity_ae_burden(
    min_comorbidities: int = Query(3, ge=0, le=5,
                                   description="Return patients with at least this many"),
):
    data = run(q.ar8_comorbidity_ae_burden, min_comorbidities=min_comorbidities)
    return envelope(data)


# ===========================================================================
# AR9 - GET /api/interventions  (by gene or protein target)
# ===========================================================================
@app.get("/api/interventions", tags=["Interventions"])
def interventions_by_target(
    gene: Optional[str] = Query(None, description="HGNC symbol, e.g. EGFR"),
    protein: Optional[str] = Query(None),
):
    if not gene and not protein:
        raise HTTPException(status_code=422,
                            detail="Provide at least one of 'gene' or 'protein'")
    data = run(q.ar9_interventions_by_target, gene=gene, protein=protein)
    return envelope(data)


# ===========================================================================
# AR10 - GET /api/analytics/ae-trend
# ===========================================================================
@app.get("/api/analytics/ae-trend", tags=["Analytics"])
def ae_trend(
    trial_id: Optional[str] = Query(None),
    intervention_type: Optional[str] = Query(None,
                                             description="e.g. Drug, Biologic, Placebo, Procedure"),
):
    data = run(q.ar10_monthly_ae_trend, trial_id=trial_id,
               intervention_type=intervention_type)
    return envelope(data)


# ---------------------------------------------------------------------------
# health check
# ---------------------------------------------------------------------------
@app.get("/", tags=["Meta"])
def root():
    return {"service": "MCRI CTMS API", "docs": "/docs", "ars": 10}