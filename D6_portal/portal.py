#!/usr/bin/env python3
"""
D6 - Data Portal (Streamlit) for the MCRI CTMS.

A read-only portal for clinicians / investigators / analysts. It consumes the
D5 FastAPI endpoints over HTTP only - it never connects to MongoDB directly.

Five required features (brief D6), each calling an API endpoint and each with at
least one interactive filter:
  1. Trial Browser           -> AR1   /api/trials
  2. Patient Search          -> AR3   /api/patients  (+ AR2 patients-in-trial)
  3. AE Monitor              -> AR4   /api/patients/{id}/adverse-events  (colour-coded)
  4. Analytics               -> AR5 / AR6 / AR10  (charts update on filter)
  5. Enrolment & Explorer    -> AR6 / AR7 / AR8 / AR9  dashboard

Run:
    pip install streamlit requests pandas
    # make sure the D5 API is running first (uvicorn app:app --reload)
    streamlit run portal.py
"""

import os
import requests
import pandas as pd
import streamlit as st

API = os.environ.get("API_BASE", "http://127.0.0.1:8000")

st.set_page_config(page_title="MCRI CTMS Portal", layout="wide")


# ---------------------------------------------------------------------------
# API helper
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def api_get(path, params=None):
    """GET a path on the API and return the parsed JSON, or raise a clean error."""
    try:
        r = requests.get(f"{API}{path}", params=params or {}, timeout=30)
    except requests.exceptions.ConnectionError:
        st.error(f"Cannot reach the API at {API}. Is the D5 server running "
                 f"(uvicorn app:app --reload)?")
        st.stop()
    if r.status_code == 404:
        return {"total": 0, "data": [], "_error": r.json().get("detail", "Not found")}
    if r.status_code == 422:
        return {"total": 0, "data": [], "_error": r.json().get("detail", "Invalid input")}
    if r.status_code >= 500:
        st.error(f"Server error: {r.text}")
        st.stop()
    return r.json()


def df_of(payload):
    return pd.json_normalize(payload.get("data", []))


# pull filter option lists once, live from the data (generalisable, not hardcoded)
@st.cache_data(ttl=300, show_spinner=False)
def trial_options():
    rows = api_get("/api/trials", {"limit": 100}).get("data", [])
    statuses = sorted({r["status"] for r in rows if r.get("status")})
    phases = sorted({r["phase"] for r in rows if r.get("phase")})
    sponsors = sorted({r["sponsor"] for r in rows if r.get("sponsor")})
    trial_ids = sorted({r["trial_id"] for r in rows})
    return statuses, phases, sponsors, trial_ids


SEVERITY_COLOURS = {
    1: "#2ecc71",  # mild - green
    2: "#a3cb38",  # moderate - light green
    3: "#f6b93b",  # severe - amber
    4: "#e55039",  # life-threatening - red
    5: "#6c0e0e",  # fatal - dark red
}


def colour_grade(val):
    try:
        return f"background-color: {SEVERITY_COLOURS.get(int(val), '#ffffff')}; color: white;"
    except (ValueError, TypeError):
        return ""


# ---------------------------------------------------------------------------
# sidebar navigation
# ---------------------------------------------------------------------------
st.sidebar.title("MCRI CTMS Portal")
st.sidebar.caption(f"API: {API}")
page = st.sidebar.radio(
    "Feature",
    ["1 · Trial Browser",
     "2 · Patient Search",
     "3 · AE Monitor",
     "4 · Analytics",
     "5 · Enrolment & Explorer"],
)

statuses, phases, sponsors, trial_ids = trial_options()


# ===========================================================================
# FEATURE 1 - Trial Browser  (AR1)
# ===========================================================================
if page.startswith("1"):
    st.header("Trial Browser")
    st.write("Filter clinical trials by status, phase, or sponsor. *(AR1 → /api/trials)*")

    c1, c2, c3 = st.columns(3)
    f_status = c1.selectbox("Status", ["(any)"] + statuses)
    f_phase = c2.selectbox("Phase", ["(any)"] + phases)
    f_sponsor = c3.selectbox("Sponsor", ["(any)"] + sponsors)

    params = {}
    if f_status != "(any)":
        params["status"] = f_status
    if f_phase != "(any)":
        params["phase"] = f_phase
    if f_sponsor != "(any)":
        params["sponsor"] = f_sponsor

    payload = api_get("/api/trials", params)
    st.caption(f"{payload['total']} trial(s) found")
    df = df_of(payload)
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No trials match these filters.")


# ===========================================================================
# FEATURE 2 - Patient Search  (AR3 + AR2)
# ===========================================================================
elif page.startswith("2"):
    st.header("Patient Search")
    mode = st.radio("Search mode", ["Across all patients (AR3)",
                                    "Within one trial (AR2)"], horizontal=True)

    if mode.startswith("Across"):
        st.write("*(AR3 → /api/patients)*")
        c1, c2, c3 = st.columns(3)
        gender = c1.selectbox("Gender", ["(any)", "Male", "Female", "Non-binary", "Prefer not to say"])
        ethnicity = c2.selectbox("Ethnicity", ["(any)", "Malay", "Chinese", "Indian",
                                               "Caucasian", "African", "Hispanic", "Other"])
        site = c3.selectbox("Site", ["(any)"] + [f"SITE-0{i}" for i in range(1, 6)])
        c4, c5 = st.columns(2)
        smoking = c4.selectbox("Smoking status", ["(any)", "Never", "Former", "Current"])
        dx = c5.text_input("Diagnosis ICD-10 code (e.g. C34.1)")

        params = {}
        for k, v in [("gender", gender), ("ethnicity", ethnicity), ("site_id", site),
                     ("smoking_status", smoking)]:
            if v != "(any)":
                params[k] = v
        if dx.strip():
            params["diagnosis_code"] = dx.strip()

        payload = api_get("/api/patients", params)
    else:
        st.write("*(AR2 → /api/trials/{trial_id}/patients)*")
        c1, c2, c3 = st.columns(3)
        trial = c1.selectbox("Trial", trial_ids)
        gender = c2.selectbox("Gender", ["(any)", "Male", "Female", "Non-binary", "Prefer not to say"])
        smoking = c3.selectbox("Smoking status", ["(any)", "Never", "Former", "Current"])
        params = {}
        if gender != "(any)":
            params["gender"] = gender
        if smoking != "(any)":
            params["smoking_status"] = smoking
        payload = api_get(f"/api/trials/{trial}/patients", params)

    st.caption(f"{payload['total']} patient(s) found")
    df = df_of(payload)
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No patients match.")


# ===========================================================================
# FEATURE 3 - AE Monitor  (AR4, colour-coded severity)
# ===========================================================================
elif page.startswith("3"):
    st.header("Adverse Event Monitor")
    st.write("Pull a patient's full AE history, colour-coded by CTCAE grade. "
             "*(AR4 → /api/patients/{id}/adverse-events)*")

    c1, c2, c3 = st.columns(3)
    pid = c1.text_input("Patient ID", value="PT-000028")
    min_grade = c2.selectbox("Minimum CTCAE grade", ["(any)", 1, 2, 3, 4, 5])
    serious_only = c3.selectbox("Serious only?", ["(any)", "Yes", "No"])

    params = {}
    if min_grade != "(any)":
        params["min_grade"] = min_grade
    if serious_only == "Yes":
        params["serious"] = "true"
    elif serious_only == "No":
        params["serious"] = "false"

    if pid.strip():
        payload = api_get(f"/api/patients/{pid.strip()}/adverse-events", params)
        if payload.get("_error"):
            st.warning(payload["_error"])
        else:
            st.caption(f"{payload['total']} adverse event(s)")
            df = df_of(payload)
            if not df.empty:
                # severity legend
                st.markdown(
                    "**Grade legend:** "
                    "🟢 1 Mild  🟩 2 Moderate  🟠 3 Severe  🔴 4 Life-threatening  🟥 5 Fatal"
                )
                styled = df.style.map(colour_grade, subset=["ctcae_grade"]) \
                    if "ctcae_grade" in df.columns else df
                st.dataframe(styled, use_container_width=True, hide_index=True)
            else:
                st.info("No adverse events for this patient with the chosen filters.")


# ===========================================================================
# FEATURE 4 - Analytics  (AR5 / AR6 / AR10, charts update on filter)
# ===========================================================================
elif page.startswith("4"):
    st.header("Analytics")

    tab1, tab2, tab3 = st.tabs(["AE by intervention type (AR5)",
                                "Enrolment progress (AR6)",
                                "Monthly AE trend (AR10)"])

    with tab1:
        st.write("*(AR5 → /api/analytics/ae-by-intervention-type)*")
        payload = api_get("/api/analytics/ae-by-intervention-type")
        df = df_of(payload)
        if not df.empty:
            df = df.set_index("intervention_type")
            metric = st.radio("Show", ["total_aes", "serious_aes", "serious_proportion"],
                              horizontal=True)
            st.bar_chart(df[metric])
            st.dataframe(df.reset_index(), use_container_width=True, hide_index=True)

    with tab2:
        st.write("*(AR6 → /api/analytics/enrolment-progress)*")
        c1, c2 = st.columns(2)
        f_sponsor = c1.selectbox("Sponsor", ["(any)"] + sponsors, key="ar6_sp")
        f_phase = c2.selectbox("Phase", ["(any)"] + phases, key="ar6_ph")
        params = {}
        if f_sponsor != "(any)":
            params["sponsor"] = f_sponsor
        if f_phase != "(any)":
            params["phase"] = f_phase
        payload = api_get("/api/analytics/enrolment-progress", params)
        df = df_of(payload)
        if not df.empty:
            chart_df = df.set_index("short_title")[["completion_pct"]]
            st.bar_chart(chart_df)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No trials match these filters.")

    with tab3:
        st.write("*(AR10 → /api/analytics/ae-trend)*")
        c1, c2 = st.columns(2)
        f_trial = c1.selectbox("Trial (optional)", ["(all)"] + trial_ids, key="ar10_t")
        f_type = c2.selectbox("Intervention type (optional)",
                              ["(all)", "Drug", "Biologic", "Placebo", "Procedure",
                               "Device", "Dietary Supplement", "Other"], key="ar10_ty")
        params = {}
        if f_trial != "(all)":
            params["trial_id"] = f_trial
        if f_type != "(all)":
            params["intervention_type"] = f_type
        payload = api_get("/api/analytics/ae-trend", params)
        df = df_of(payload)
        if not df.empty:
            df["period"] = df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2)
            df = df.sort_values("period").set_index("period")
            st.line_chart(df[["ae_count", "serious_count"]])
            st.dataframe(df.reset_index(), use_container_width=True, hide_index=True)
        else:
            st.info("No adverse events for this scope.")


# ===========================================================================
# FEATURE 5 - Enrolment & Explorer dashboard  (AR6 / AR7 / AR8 / AR9)
# ===========================================================================
elif page.startswith("5"):
    st.header("Enrolment & Explorer Dashboard")

    tab1, tab2, tab3 = st.tabs(["Safety matrix (AR7)",
                                "Comorbidity burden (AR8)",
                                "Target explorer (AR9)"])

    with tab1:
        st.write("Causality × CTCAE-grade cross-tab for one trial. "
                 "*(AR7 → /api/trials/{id}/safety-matrix)*")
        trial = st.selectbox("Trial", trial_ids, key="ar7_t")
        payload = api_get(f"/api/trials/{trial}/safety-matrix")
        rows = payload.get("data", [])
        if rows:
            # build a causality x grade matrix
            matrix = {}
            for row in rows:
                causality = row["causality"]
                matrix.setdefault(causality, {g: 0 for g in range(1, 6)})
                for cell in row["grades"]:
                    matrix[causality][cell["grade"]] = cell["count"]
            mdf = pd.DataFrame(matrix).T
            mdf.columns = [f"Grade {c}" for c in mdf.columns]
            st.dataframe(mdf, use_container_width=True)
            st.caption("Rows = causality, Columns = CTCAE grade, cells = AE count")
        else:
            st.info("No adverse events recorded for this trial.")

    with tab2:
        st.write("Patients above a comorbidity threshold with their AE burden. "
                 "*(AR8 → /api/analytics/comorbidity-ae-burden)*")
        thr = st.slider("Minimum comorbidities", 0, 5, 3)
        payload = api_get("/api/analytics/comorbidity-ae-burden",
                          {"min_comorbidities": thr})
        df = df_of(payload)
        st.caption(f"{payload['total']} patient(s)")
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.bar_chart(df.set_index("patient_id")[["total_aes", "serious_aes"]])
        else:
            st.info("No patients above this threshold.")

    with tab3:
        st.write("Find interventions by molecular target. "
                 "*(AR9 → /api/interventions)*")
        c1, c2 = st.columns(2)
        gene = c1.text_input("Target gene (e.g. EGFR, PD-L1, VEGFR)")
        protein = c2.text_input("Target protein (optional)")
        if gene.strip() or protein.strip():
            params = {}
            if gene.strip():
                params["gene"] = gene.strip()
            if protein.strip():
                params["protein"] = protein.strip()
            payload = api_get("/api/interventions", params)
            if payload.get("_error"):
                st.warning(payload["_error"])
            else:
                st.caption(f"{payload['total']} intervention(s)")
                df = df_of(payload)
                if not df.empty:
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("No interventions hit that target.")
        else:
            st.info("Enter a gene or protein to search.")