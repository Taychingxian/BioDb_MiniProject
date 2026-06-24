#!/usr/bin/env python3
"""
D4 - Analytical Queries (AR1 - AR10) for the MCRI CTMS.

One MongoDB aggregation pipeline per analytical requirement. Each is written as a
PARAMETERISED function (the same pipelines are reused by the D5 FastAPI endpoints),
so it works for any valid input, not just the example shown. Running this file
executes every AR once with a real example drawn from the dataset and prints the
result plus a one-line explanation of what it reveals.

Run:
    pip install pymongo
    python queries.py --mongo "mongodb+srv://USER:PASS@cluster0.xxxx.mongodb.net/" --db ctms

"""

import argparse
import json
from datetime import datetime
from pymongo import MongoClient


# ===========================================================================
# AR1 - Filter trials by status and/or phase (and/or sponsor)
# ===========================================================================
def ar1_filter_trials(db, status=None, phase=None, sponsor=None, page=1, limit=20):
    """Retrieve trials filtered by any combination of status, phase, sponsor.
    All filters optional; absent filters are simply not applied (generalizable)."""
    match = {}
    if status:
        match["status"] = status
    if phase:
        match["phase"] = phase
    if sponsor:
        match["sponsor"] = sponsor

    pipeline = [
        {"$match": match},
        {"$sort": {"trial_id": 1}},
        {"$skip": (page - 1) * limit},
        {"$limit": limit},
        {"$project": {
            "_id": 0, "trial_id": 1, "short_title": 1,
            "phase": 1, "status": 1, "sponsor": 1,
            "enrolment_target": 1, "enrolled_count": 1,
        }},
    ]
    return list(db.trials.aggregate(pipeline))


# ===========================================================================
# AR2 - Retrieve all patients for a specific trial (narrowable by attributes)
# ===========================================================================
def ar2_patients_in_trial(db, trial_id, gender=None, smoking_status=None,
                          site_id=None, page=1, limit=50):
    """All patients enrolled in a given trial. The patient<->trial link lives on
    the patient side (enrolled_trials array), so we match into that array."""
    match = {"enrolled_trials": trial_id}
    if gender:
        match["gender"] = gender
    if smoking_status:
        match["smoking_status"] = smoking_status
    if site_id:
        match["site_id"] = site_id

    pipeline = [
        {"$match": match},
        {"$sort": {"patient_id": 1}},
        {"$skip": (page - 1) * limit},
        {"$limit": limit},
        {"$project": {
            "_id": 0, "patient_id": 1, "name": 1, "gender": 1,
            "ethnicity": 1, "smoking_status": 1, "bmi": 1,
            "site_id": 1, "diagnosis.icd10_code": 1,
        }},
    ]
    return list(db.patients.aggregate(pipeline))


# ===========================================================================
# AR3 - Search patients by demographic / clinical criteria
# ===========================================================================
def ar3_search_patients(db, gender=None, ethnicity=None, site_id=None,
                        smoking_status=None, diagnosis_code=None,
                        page=1, limit=50):
    """Free combination search across the patient population. Any subset of
    criteria may be supplied; the primary diagnosis is matched on its ICD-10 code."""
    match = {}
    if gender:
        match["gender"] = gender
    if ethnicity:
        match["ethnicity"] = ethnicity
    if site_id:
        match["site_id"] = site_id
    if smoking_status:
        match["smoking_status"] = smoking_status
    if diagnosis_code:
        match["diagnosis.icd10_code"] = diagnosis_code

    pipeline = [
        {"$match": match},
        {"$sort": {"patient_id": 1}},
        {"$skip": (page - 1) * limit},
        {"$limit": limit},
        {"$project": {
            "_id": 0, "patient_id": 1, "name": 1, "gender": 1,
            "ethnicity": 1, "site_id": 1, "smoking_status": 1,
            "diagnosis.icd10_code": 1, "diagnosis.description": 1,
        }},
    ]
    return list(db.patients.aggregate(pipeline))


# ===========================================================================
# AR4 - Retrieve all adverse events for a patient (filterable by severity)
# ===========================================================================
def ar4_patient_ae_history(db, patient_id, min_grade=None, serious=None,
                           intervention_id=None):
    """A patient's full AE history across ALL their trials. Optional filters
    narrow by minimum CTCAE grade, seriousness, or a specific intervention."""
    match = {"patient_id": patient_id}
    if min_grade is not None:
        match["ctcae_grade"] = {"$gte": min_grade}
    if serious is not None:
        match["serious"] = serious
    if intervention_id:
        match["intervention_id"] = intervention_id

    pipeline = [
        {"$match": match},
        {"$sort": {"onset_date": 1}},
        {"$project": {
            "_id": 0, "ae_id": 1, "trial_id": 1, "intervention_id": 1,
            "event_name": 1, "ctcae_grade": 1, "serious": 1,
            "outcome": 1, "causality": 1, "onset_date": 1,
        }},
    ]
    return list(db.adverse_events.aggregate(pipeline))


# ===========================================================================
# AR5 - AE summary grouped by intervention TYPE (count + % serious)
# ===========================================================================
def ar5_ae_by_intervention_type(db):
    """Join each AE to its intervention to get the intervention TYPE, then group.
    Returns per-type total AEs, serious AEs, and the serious proportion.
    This is the AE -> intervention join the recording emphasises."""
    pipeline = [
        {"$lookup": {
            "from": "interventions",
            "localField": "intervention_id",
            "foreignField": "intervention_id",
            "as": "intv",
        }},
        {"$unwind": "$intv"},
        {"$group": {
            "_id": "$intv.type",
            "total_aes": {"$sum": 1},
            "serious_aes": {"$sum": {"$cond": ["$serious", 1, 0]}},
        }},
        {"$project": {
            "_id": 0,
            "intervention_type": "$_id",
            "total_aes": 1,
            "serious_aes": 1,
            "serious_proportion": {
                "$round": [{"$divide": ["$serious_aes", "$total_aes"]}, 3]
            },
        }},
        {"$sort": {"total_aes": -1}},
    ]
    return list(db.adverse_events.aggregate(pipeline))


# ===========================================================================
# AR6 - Enrolment progress across trials (% of target), filterable
# ===========================================================================
def ar6_enrolment_progress(db, sponsor=None, phase=None, status=None):
    """Enrolment completion as a percentage of target per trial.
    Optional filters scope by sponsor / phase / status."""
    match = {}
    if sponsor:
        match["sponsor"] = sponsor
    if phase:
        match["phase"] = phase
    if status:
        match["status"] = status

    pipeline = [
        {"$match": match},
        {"$project": {
            "_id": 0, "trial_id": 1, "short_title": 1,
            "phase": 1, "status": 1, "sponsor": 1,
            "enrolment_target": 1, "enrolled_count": 1,
            "completion_pct": {
                "$round": [
                    {"$multiply": [
                        {"$cond": [
                            {"$gt": ["$enrolment_target", 0]},
                            {"$divide": ["$enrolled_count", "$enrolment_target"]},
                            0,
                        ]},
                        100,
                    ]},
                    1,
                ]
            },
        }},
        {"$sort": {"completion_pct": -1}},
    ]
    return list(db.trials.aggregate(pipeline))


# ===========================================================================
# AR7 - AE causality x CTCAE-grade matrix for a given trial
# ===========================================================================
def ar7_causality_severity_matrix(db, trial_id):
    """Cross-tabulation of AEs by causality (rows) and CTCAE grade (cols) for one
    trial - the 'safety matrix' the data monitoring committee needs."""
    pipeline = [
        {"$match": {"trial_id": trial_id}},
        {"$group": {
            "_id": {"causality": "$causality", "grade": "$ctcae_grade"},
            "count": {"$sum": 1},
        }},
        {"$group": {
            "_id": "$_id.causality",
            "grades": {"$push": {"grade": "$_id.grade", "count": "$count"}},
            "row_total": {"$sum": "$count"},
        }},
        {"$project": {
            "_id": 0, "causality": "$_id",
            "grades": 1, "row_total": 1,
        }},
        {"$sort": {"causality": 1}},
    ]
    return list(db.adverse_events.aggregate(pipeline))


# ===========================================================================
# AR8 - Patient comorbidity burden vs AE burden (threshold)
# ===========================================================================
def ar8_comorbidity_ae_burden(db, min_comorbidities=3):
    """Patients whose comorbidity count exceeds a threshold, with their total
    and serious AE counts. Joins patients -> adverse_events."""
    pipeline = [
        {"$project": {
            "_id": 0, "patient_id": 1, "name": 1,
            "comorbidity_count": {"$size": {"$ifNull": ["$comorbidities", []]}},
        }},
        {"$match": {"comorbidity_count": {"$gte": min_comorbidities}}},
        {"$lookup": {
            "from": "adverse_events",
            "localField": "patient_id",
            "foreignField": "patient_id",
            "as": "aes",
        }},
        {"$project": {
            "patient_id": 1, "name": 1, "comorbidity_count": 1,
            "total_aes": {"$size": "$aes"},
            "serious_aes": {
                "$size": {
                    "$filter": {
                        "input": "$aes",
                        "as": "ae",
                        "cond": "$$ae.serious",
                    }
                }
            },
        }},
        {"$sort": {"comorbidity_count": -1, "serious_aes": -1}},
    ]
    return list(db.patients.aggregate(pipeline))


# ===========================================================================
# AR9 - Interventions by gene or protein target (+ trial context)
# ===========================================================================
def ar9_interventions_by_target(db, gene=None, protein=None):
    """All interventions targeting a given gene symbol or protein, with their
    parent trial context and regulatory status. At least one of gene/protein
    should be supplied."""
    match = {}
    if gene:
        match["target_gene"] = gene
    if protein:
        match["target_protein"] = protein

    pipeline = [
        {"$match": match},
        {"$lookup": {
            "from": "trials",
            "localField": "trial_id",
            "foreignField": "trial_id",
            "as": "trial",
        }},
        {"$unwind": "$trial"},
        {"$project": {
            "_id": 0, "intervention_id": 1, "name": 1, "type": 1,
            "target_gene": 1, "target_protein": 1,
            "regulatory_status": 1, "arm_label": 1,
            "trial_id": 1,
            "trial_title": "$trial.short_title",
            "trial_status": "$trial.status",
        }},
        {"$sort": {"intervention_id": 1}},
    ]
    return list(db.interventions.aggregate(pipeline))


# ===========================================================================
# AR10 - Monthly AE trend over time (year-month time series)
# ===========================================================================
def ar10_monthly_ae_trend(db, trial_id=None, intervention_type=None):
    """Time series of AE counts grouped by year+month. Optionally scoped to one
    trial, or to an intervention type (which needs the AE->intervention join)."""
    pipeline = []
    match = {}
    if trial_id:
        match["trial_id"] = trial_id

    if intervention_type:
        pipeline += [
            {"$lookup": {
                "from": "interventions",
                "localField": "intervention_id",
                "foreignField": "intervention_id",
                "as": "intv",
            }},
            {"$unwind": "$intv"},
            {"$match": {"intv.type": intervention_type}},
        ]
    if match:
        pipeline.append({"$match": match})

    pipeline += [
        {"$group": {
            "_id": {
                "year": {"$year": "$onset_date"},
                "month": {"$month": "$onset_date"},
            },
            "ae_count": {"$sum": 1},
            "serious_count": {"$sum": {"$cond": ["$serious", 1, 0]}},
        }},
        {"$project": {
            "_id": 0,
            "year": "$_id.year",
            "month": "$_id.month",
            "ae_count": 1,
            "serious_count": 1,
        }},
        {"$sort": {"year": 1, "month": 1}},
    ]
    return list(db.adverse_events.aggregate(pipeline))


# ===========================================================================
# demonstration harness
# ===========================================================================
def _show(title, explanation, result, limit=8):
    print("\n" + "=" * 78)
    print(title)
    print("-" * 78)
    print("What it reveals:", explanation)
    print(f"Rows returned: {len(result)}  (showing up to {limit})")
    for row in result[:limit]:
        print("  ", json.dumps(row, default=str, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", default="mongodb://localhost:27017")
    ap.add_argument("--db", default="ctms")
    args = ap.parse_args()
    db = MongoClient(args.mongo)[args.db]

    _show("AR1  Filter trials by status/phase  (status='Recruiting')",
          "Lists trials matching the filter - the core trial browser query.",
          ar1_filter_trials(db, status="Recruiting"))

    # pick a real trial id to demo AR2 / AR7 / AR10
    any_trial = db.trials.find_one({}, {"trial_id": 1})
    trial_id = any_trial["trial_id"] if any_trial else "NCT-20240003"

    _show(f"AR2  Patients in a trial  (trial_id='{trial_id}')",
          "Demographics of everyone enrolled in one trial; narrowable by attributes.",
          ar2_patients_in_trial(db, trial_id))

    _show("AR3  Search patients  (gender='Female', smoking_status='Never')",
          "Population search across any demographic/clinical combination.",
          ar3_search_patients(db, gender="Female", smoking_status="Never"))

    # patient with the most AEs for a meaningful AR4
    top_patient = next(iter(db.adverse_events.aggregate([
        {"$group": {"_id": "$patient_id", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 1},
    ])), None)
    pid = top_patient["_id"] if top_patient else "PT-000028"

    _show(f"AR4  Patient AE history  (patient_id='{pid}')",
          "Every AE for one patient across all trials; filterable by severity.",
          ar4_patient_ae_history(db, pid))

    _show("AR5  AE summary by intervention type",
          "Which intervention types generate the most AEs and how many are serious.",
          ar5_ae_by_intervention_type(db))

    _show("AR6  Enrolment progress across trials",
          "Completion % vs target per trial - the enrolment tracking dashboard.",
          ar6_enrolment_progress(db))

    _show(f"AR7  Causality x grade safety matrix  (trial_id='{trial_id}')",
          "Cross-tab of AEs by causality and CTCAE grade for one trial.",
          ar7_causality_severity_matrix(db, trial_id))

    _show("AR8  Comorbidity vs AE burden  (>= 3 comorbidities)",
          "High-comorbidity patients and their total/serious AE load.",
          ar8_comorbidity_ae_burden(db, min_comorbidities=3))

    # a gene that exists in the data
    g = db.interventions.find_one({"target_gene": {"$ne": None}}, {"target_gene": 1})
    gene = g["target_gene"] if g else "EGFR"

    _show(f"AR9  Interventions by target  (gene='{gene}')",
          "All interventions hitting a molecular target, with trial context.",
          ar9_interventions_by_target(db, gene=gene))

    _show("AR10 Monthly AE trend (all trials)",
          "Year-month time series of AE counts to spot reporting peaks.",
          ar10_monthly_ae_trend(db))

    print("\n" + "=" * 78)
    print("All 10 ARs executed.")

 
if __name__ == "__main__":
    main()