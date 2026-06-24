#!/usr/bin/env python3
"""
D2 — Data Ingestion for the MCRI CTMS.

Reads the four flat CSV files, reshapes flat columns into the embedded objects /
arrays defined by the D1 $jsonSchema validators, enforces referential
consistency (every foreign ID must resolve to a real document), creates the four
collections WITH their validators, loads the data, and prints a document count
per collection.

Run:
    pip install pymongo
    python ingest.py --mongo mongodb://localhost:27017 --db ctms \
                     --csv-dir ./data --schema-dir ./D1_schemas

Transformations applied (flat CSV -> nested Mongo document):
  patients:   diagnosis_* -> diagnosis{},  contact_* -> contact_info{},
              comorbidities "a|b" -> [a, b],  enrolled_trials "x|y" -> [x, y]
  trials:     arms "Arm A:Experimental|..." -> [{arm_label, arm_type}],
              conditions/sites/secondary_endpoints "a|b" -> [a, b],
              ethical_* -> ethical_approval{}
  interventions: dosage_* -> dosage{},  empty target_gene/protein -> null
  adverse_events: lab_* -> lab_values{} or null,  empty resolution_date -> null,
              "TRUE"/"FALSE" -> bool
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

from pymongo import MongoClient, ASCENDING
from pymongo.errors import CollectionInvalid, WriteError, BulkWriteError


# ---------------------------------------------------------------------------
# small parsing helpers
# ---------------------------------------------------------------------------
def split_pipe(value):
    """'a|b|c' -> ['a','b','c'];  '' -> []."""
    if value is None:
        return []
    value = value.strip()
    if value == "":
        return []
    return [part.strip() for part in value.split("|") if part.strip() != ""]


def to_date(value):
    """ISO 'YYYY-MM-DD' (or full ISO) -> datetime; '' -> None."""
    if value is None or value.strip() == "":
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {value!r}")


def to_int(value):
    return None if value is None or value.strip() == "" else int(float(value))


def to_float(value):
    return None if value is None or value.strip() == "" else float(value)


def to_bool(value):
    return value.strip().upper() == "TRUE"


def or_null(value):
    """Empty string -> None, else stripped string."""
    if value is None:
        return None
    value = value.strip()
    return None if value == "" else value


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# row -> document transformers (flat CSV -> nested Mongo doc)
# ---------------------------------------------------------------------------
def build_patient(r):
    doc = {
        "patient_id": r["patient_id"],
        "name": r["name"],
        "date_of_birth": to_date(r["date_of_birth"]),
        "gender": r["gender"],
        "ethnicity": r["ethnicity"],
        "blood_type": r["blood_type"],
        "bmi": to_float(r["bmi"]),
        "smoking_status": r["smoking_status"],
        # flat diagnosis_* columns -> embedded object
        "diagnosis": {
            "icd10_code": r["diagnosis_icd10"],
            "description": r["diagnosis_desc"],
            "diagnosed_on": to_date(r["diagnosed_on"]),
        },
        # pipe string -> array (0-5 entries; may be empty)
        "comorbidities": split_pipe(r["comorbidities"]),
        "site_id": r["site_id"],
        # reference side of the many-to-many patient<->trial link
        "enrolled_trials": split_pipe(r["enrolled_trials"]),
        # flat contact_* columns -> embedded object
        "contact_info": {
            "email": r["contact_email"],
            "phone": r["contact_phone"],
            "emergency_contact": r["emergency_contact"],
        },
        "created_at": to_date(r["created_at"]),
    }
    # carry enrolment_date if present (used later for onset_date validation)
    if r.get("enrolment_date", "").strip():
        doc["enrolment_date"] = to_date(r["enrolment_date"])
    return doc


def build_trial(r):
    # 'Arm A:Experimental|Arm B:Placebo Comparator' -> embedded array of objects
    arms = []
    for seg in split_pipe(r["arms"]):
        label, _, arm_type = seg.partition(":")
        arms.append({"arm_label": label.strip(), "arm_type": arm_type.strip()})

    doc = {
        "trial_id": r["trial_id"],
        "title": r["title"],
        "short_title": r["short_title"],
        "phase": r["phase"],
        "status": r["status"],
        "sponsor": r["sponsor"],
        "conditions": split_pipe(r["conditions"]),
        "start_date": to_date(r["start_date"]),
        "estimated_end_date": to_date(r["estimated_end_date"]),
        "enrolment_target": to_int(r["enrolment_target"]),
        "enrolled_count": to_int(r["enrolled_count"]),
        "arms": arms,
        "primary_endpoint": r.get("primary_endpoint", ""),
        "secondary_endpoints": split_pipe(r.get("secondary_endpoints", "")),
        "sites": split_pipe(r["sites"]),
        # flat ethical_* columns -> embedded object
        "ethical_approval": {
            "approval_id": r["ethical_approval_id"],
            "committee": r["ethical_committee"],
            "approved_on": to_date(r["ethical_approved_on"]),
        },
        "created_at": to_date(r["created_at"]),
    }
    # interventions array is filled in later (back-reference from interventions)
    doc["interventions"] = []
    return doc


def build_intervention(r):
    return {
        "intervention_id": r["intervention_id"],
        "trial_id": r["trial_id"],
        "arm_label": r["arm_label"],
        "name": r["name"],
        "type": r["type"],
        "mechanism": r.get("mechanism", ""),
        # flat dosage_* columns -> embedded object
        "dosage": {
            "amount": to_float(r["dosage_amount"]),
            "unit": or_null(r["dosage_unit"]),
            "frequency": or_null(r["dosage_frequency"]),
            "route": or_null(r["dosage_route"]),
        },
        "duration_weeks": to_int(r["duration_weeks"]),
        # empty -> null (e.g. placebo has no target)
        "target_gene": or_null(r["target_gene"]),
        "target_protein": or_null(r["target_protein"]),
        "regulatory_status": r["regulatory_status"],
        "created_at": to_date(r["created_at"]),
    }


def build_adverse_event(r):
    # lab_* columns -> embedded object, or null when no lab data
    lab = None
    if r["lab_value"].strip() != "":
        lab = {
            "test_name": r["lab_test_name"],
            "value": to_float(r["lab_value"]),
            "unit": r["lab_unit"],
            "reference_range": r["lab_reference_range"],
        }
    return {
        "ae_id": r["ae_id"],
        "patient_id": r["patient_id"],
        "trial_id": r["trial_id"],
        "intervention_id": r["intervention_id"],
        "event_name": r["event_name"],
        "system_organ_class": r["system_organ_class"],
        "ctcae_grade": to_int(r["ctcae_grade"]),
        "onset_date": to_date(r["onset_date"]),
        "resolution_date": to_date(r["resolution_date"]),  # '' -> None
        "outcome": r["outcome"],
        "serious": to_bool(r["serious"]),
        "action_taken": r["action_taken"],
        "causality": r["causality"],
        "lab_values": lab,
        "reported_by": r["reported_by"],
        "created_at": to_date(r["created_at"]),
    }


# ---------------------------------------------------------------------------
# referential consistency (every foreign ID must resolve)
# ---------------------------------------------------------------------------
def check_referential_integrity(patients, trials, interventions, aes):
    pids = {p["patient_id"] for p in patients}
    tids = {t["trial_id"] for t in trials}
    iids = {i["intervention_id"] for i in interventions}
    arms_by_trial = {t["trial_id"]: {a["arm_label"] for a in t["arms"]} for t in trials}

    errors = []

    # patient.enrolled_trials -> trials
    for p in patients:
        for tid in p["enrolled_trials"]:
            if tid not in tids:
                errors.append(f"patient {p['patient_id']} enrolled in missing trial {tid}")

    # intervention.trial_id -> trials, arm_label -> that trial's arms
    for i in interventions:
        if i["trial_id"] not in tids:
            errors.append(f"intervention {i['intervention_id']} -> missing trial {i['trial_id']}")
        elif i["arm_label"] not in arms_by_trial[i["trial_id"]]:
            errors.append(
                f"intervention {i['intervention_id']} arm '{i['arm_label']}' "
                f"not in trial {i['trial_id']}"
            )

    # AE: all three references mandatory and must resolve
    for a in aes:
        if a["patient_id"] not in pids:
            errors.append(f"AE {a['ae_id']} -> missing patient {a['patient_id']}")
        if a["trial_id"] not in tids:
            errors.append(f"AE {a['ae_id']} -> missing trial {a['trial_id']}")
        if a["intervention_id"] not in iids:
            errors.append(f"AE {a['ae_id']} -> missing intervention {a['intervention_id']}")

    return errors


def check_cross_field_rules(trials, patients, aes):
    """Rules JSON Schema can't express (cross-field / cross-collection)."""
    warnings = []
    for t in trials:
        if t["enrolled_count"] is not None and t["enrolment_target"] is not None:
            if t["enrolled_count"] > t["enrolment_target"]:
                warnings.append(
                    f"trial {t['trial_id']} enrolled_count "
                    f"{t['enrolled_count']} > target {t['enrolment_target']}"
                )
    enrol = {p["patient_id"]: p.get("enrolment_date") for p in patients}
    for a in aes:
        ed = enrol.get(a["patient_id"])
        if ed and a["onset_date"] and a["onset_date"] < ed:
            warnings.append(f"AE {a['ae_id']} onset before patient enrolment")
    return warnings


# ---------------------------------------------------------------------------
# collection creation with $jsonSchema validators
# ---------------------------------------------------------------------------
def load_validator(schema_dir, filename):
    with open(os.path.join(schema_dir, filename), encoding="utf-8") as fh:
        return json.load(fh)


def create_collection(db, name, validator):
    if name in db.list_collection_names():
        db.drop_collection(name)
    db.create_collection(name, validator=validator, validationLevel="strict")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", default="mongodb://localhost:27017")
    ap.add_argument("--db", default="ctms")
    ap.add_argument("--csv-dir", default=".")
    ap.add_argument("--schema-dir", default="./D1_schemas")
    args = ap.parse_args()

    # 1. read raw CSVs
    patients = [build_patient(r) for r in read_csv(os.path.join(args.csv_dir, "ctms_patients.csv"))]
    trials = [build_trial(r) for r in read_csv(os.path.join(args.csv_dir, "ctms_trials.csv"))]
    interventions = [build_intervention(r) for r in read_csv(os.path.join(args.csv_dir, "ctms_interventions.csv"))]
    aes = [build_adverse_event(r) for r in read_csv(os.path.join(args.csv_dir, "ctms_adverse_events.csv"))]

    # 2. fill trial.interventions back-references
    by_trial = {}
    for i in interventions:
        by_trial.setdefault(i["trial_id"], []).append(i["intervention_id"])
    for t in trials:
        t["interventions"] = sorted(by_trial.get(t["trial_id"], []))

    # 3. referential consistency BEFORE inserting anything
    errors = check_referential_integrity(patients, trials, interventions, aes)
    if errors:
        print("REFERENTIAL INTEGRITY FAILED — aborting, nothing inserted:")
        for e in errors[:20]:
            print("  -", e)
        print(f"  ...{len(errors)} total" if len(errors) > 20 else "")
        sys.exit(1)
    print("Referential consistency OK: all foreign IDs resolve.")

    for w in check_cross_field_rules(trials, patients, aes):
        print("  cross-field warning:", w)

    # 4. connect, create validated collections, insert
    client = MongoClient(args.mongo)
    db = client[args.db]

    specs = [
        ("patients", "patients.schema.json", patients, "patient_id"),
        ("trials", "trials.schema.json", trials, "trial_id"),
        ("interventions", "interventions.schema.json", interventions, "intervention_id"),
        ("adverse_events", "adverse_events.schema.json", aes, "ae_id"),
    ]

    for name, schema_file, docs, key in specs:
        validator = load_validator(args.schema_dir, schema_file)
        create_collection(db, name, validator)
        try:
            db[name].insert_many(docs, ordered=False)
        except (WriteError, BulkWriteError) as exc:
            print(f"\nSchema validation rejected a document in '{name}':")
            print(exc.details if hasattr(exc, "details") else exc)
            sys.exit(1)
        db[name].create_index([(key, ASCENDING)], unique=True)

    # helpful secondary indexes for the AR queries
    db.patients.create_index([("enrolled_trials", ASCENDING)])
    db.patients.create_index([("site_id", ASCENDING)])
    db.interventions.create_index([("trial_id", ASCENDING)])
    db.interventions.create_index([("target_gene", ASCENDING)])
    db.adverse_events.create_index([("patient_id", ASCENDING)])
    db.adverse_events.create_index([("trial_id", ASCENDING)])
    db.adverse_events.create_index([("intervention_id", ASCENDING)])

    # 5. print per-collection counts
    print("\nIngestion complete. Document counts:")
    for name, _, _, _ in specs:
        print(f"  {name:<16} {db[name].count_documents({}):>5}")


if __name__ == "__main__":
    main()