"""
EQS Measurement Analyser -- Streamlit interface.

Five pages, in the order the work happens:
    1 Home                     what this is, what it needs, what it will not do
    2 Upload and configuration  the file and every input the analysis needs
    3 Data validation           what is in the file, and what is wrong with it
    4 Analysis results          figures, tables, preliminary size guidance
    5 Downloads                 ZIP, spreadsheet, PDF, individual figures

Start it with:  streamlit run app.py
"""

from __future__ import annotations

import os
import threading
from datetime import datetime

import pandas as pd
import streamlit as st

from src import adapters, analysis, config as cfg, file_detection as fd
from src import reporting, sizing as sizing_mod, validation as validation_mod

st.set_page_config(page_title="EQS Measurement Analyser",
                   page_icon="Chart", layout="wide")

PAGES = ["1 · Home",
         "2 · Upload and configuration",
         "3 · Data validation",
         "4 · Analysis results",
         "5 · Downloads"]

BUNDLED_IRRADIATION = {
    "Kampala": "sample_data/irradiation_kampala.csv",
    "Mbale": "sample_data/irradiation_mbale.csv",
}


# ---------------------------------------------------------------------------
# session state
# ---------------------------------------------------------------------------

@st.cache_resource
def run_lock() -> threading.Lock:
    """One lock per server process.

    The generated plotting modules hold their configuration and dataframes in
    module-level globals, exactly as the notebooks did. Two runs at once would
    overwrite each other, so on a shared instance the second one queues.
    """
    return threading.Lock()


def state(key, default=None):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


state("measurement")          # (name, bytes)
state("irradiation")          # (name, bytes)
state("profile")
state("validation")
state("dataframe")
state("suggestions", {})
state("result")
state("session_obj")
state("page", PAGES[0])


def goto(page):
    """Ask for a page change.

    Streamlit refuses to let session_state.page be written once the radio
    widget that uses that key exists, so the request is parked and applied at
    the top of the next run, before the widget is created.
    """
    st.session_state._pending_page = page


# apply a parked page change -- must happen before the radio below
if "_pending_page" in st.session_state:
    st.session_state.page = st.session_state.pop("_pending_page")

# tidy up anything an earlier session left behind
analysis.Session.sweep_stale()


# ---------------------------------------------------------------------------
# navigation
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("EQS Measurement Analyser")
    st.caption("Econ and Shelly load profiles")
    st.radio("Page", PAGES, key="page", label_visibility="collapsed")
    st.divider()

    m = st.session_state.measurement
    st.markdown("**Measurement file**")
    st.caption(m[0] if m else "none loaded")
    prof = st.session_state.profile
    if prof is not None and prof.ok:
        st.caption("%s · %s · %d columns"
                   % (prof.device or "device unknown",
                      "'%s' separated" % prof.delimiter, len(prof.columns)))
    v = st.session_state.validation
    if v is not None:
        if v.errors:
            st.error("%d blocking issue(s)" % len(v.errors))
        elif v.warnings:
            st.warning("%d warning(s)" % len(v.warnings))
        else:
            st.success("Validation clean")
    st.divider()
    st.caption("Uploaded files stay in a temporary folder for this session "
               "only and are never committed or stored.")

page = st.session_state.page


# ===========================================================================
# 1 · HOME
# ===========================================================================

if page == PAGES[0]:
    st.title("EQS Measurement Analyser")
    st.markdown(
        "Upload a load-profile export, set the plant details, and get the "
        "full set of measurement graphs, the energy and PV-yield summaries, "
        "and a preliminary comparison of candidate system sizes.")

    st.subheader("What it accepts")
    left, right = st.columns(2)
    with left:
        st.markdown(
            "**Econ power-quality logger**  \n"
            "Semicolon-separated CSV, Windows encoding, `Time` column as "
            "`DD/MM/YYYY HH:MM:SS`.  \n"
            "Produces **43 figures** including voltage THD and frequency.")
    with right:
        st.markdown(
            "**Shelly energy meter**  \n"
            "Comma-separated UTF-8 CSV, `timestamp` column as Unix epoch "
            "seconds.  \n"
            "Produces **32 figures**. The meter does not measure reactive "
            "power, THD or frequency, so those charts do not exist for it.")
    st.markdown(
        "Both also need an **irradiation CSV** — one row per hour, "
        "`Time,G [W/m²]`. Kampala and Mbale are bundled.")

    st.subheader("What it does with your data")
    st.markdown(
        "- Files are held in a temporary folder unique to your session and "
        "deleted when you clear the analysis.\n"
        "- Nothing is written to the repository, and no measurement file is "
        "ever committed to version control.\n"
        "- The analysis runs on the machine hosting this app. If that is a "
        "public cloud service, treat the upload accordingly.\n"
        "- Data is never silently altered. Rows are not dropped, blanks are "
        "not filled, and outliers are not removed. Anything unusual is "
        "reported on the validation page and left in place.")

    st.subheader("What it will not tell you")
    st.warning(
        "**System sizes are preliminary and require engineering review.** "
        "The original analysis contains no approved sizing rule. This tool "
        "ranks the sizes you enter against the two measures that analysis "
        "already produces — how much of the generation is used on site, and "
        "how much of the load it covers — using placeholder thresholds that "
        "carry no engineering authority. Roof area, orientation, inverter "
        "and transformer limits, tariff and payback are not considered "
        "anywhere in this tool.", icon="⚠")

    st.divider()
    st.button("Start — upload a file", type="primary",
              on_click=goto, args=(PAGES[1],))


# ===========================================================================
# 2 · UPLOAD AND CONFIGURATION
# ===========================================================================

elif page == PAGES[1]:
    st.title("Upload and configuration")

    # --- device --------------------------------------------------------
    st.subheader("Measurement source")
    options = ["Auto-detect"] + [label for _, label in adapters.choices()]
    picked = st.radio("Device", options, horizontal=True,
                      label_visibility="collapsed")

    # --- measurement file ------------------------------------------------
    st.subheader("Measurement file")
    upload = st.file_uploader(
        "Measurement CSV, or the Excel workbook one was saved as "
        "(maximum %d MB)" % cfg.MAX_UPLOAD_MB,
        type=["csv", "txt", "xlsx", "xlsm"])

    if upload is not None:
        data = upload.getvalue()
        if len(data) > cfg.MAX_UPLOAD_MB * 1024 * 1024:
            st.error("That file is %.0f MB. The limit is %d MB."
                     % (len(data) / 1e6, cfg.MAX_UPLOAD_MB))
            st.stop()
        if (st.session_state.measurement is None
                or st.session_state.measurement[1] != data):
            st.session_state.measurement = (upload.name, data)
            st.session_state.profile = fd.profile_file(data, upload.name)
            st.session_state.result = None
            st.session_state.validation = None

    if st.session_state.measurement is None:
        st.info("Upload a measurement CSV to continue.")
        st.stop()

    name, data = st.session_state.measurement
    profile = st.session_state.profile

    if not profile.ok:
        st.error(profile.error)
        st.stop()

    if profile.from_workbook:
        st.info("This was uploaded as an Excel workbook: %s. The readings are "
                "unchanged." % profile.workbook_note, icon="\N{MEMO}")

    # --- resolve the device ---------------------------------------------
    label_to_name = {label: n for n, label in adapters.choices()}
    if picked == "Auto-detect":
        if profile.device and profile.device_confidence == "certain":
            device = profile.device
            st.success("Detected **%s** — %s"
                       % (adapters.get(device).LABEL, profile.device_reason))
        elif profile.device:
            device = profile.device
            st.warning("Probably **%s** — %s. Confirm the device above if "
                       "this is wrong."
                       % (adapters.get(device).LABEL, profile.device_reason))
        else:
            st.error("Could not tell which logger produced this file: %s. "
                     "Choose the device above."
                     % profile.device_reason)
            st.stop()
    else:
        device = label_to_name[picked]
        if profile.device and profile.device != device:
            st.warning("You chose %s, but the columns look like %s. "
                       "The analysis will use your choice and will very "
                       "likely fail on the next page."
                       % (adapters.get(device).LABEL,
                          adapters.get(profile.device).LABEL))

    adapter = adapters.get(device)
    if adapter.NOT_MEASURED:
        missing = list(adapter.NOT_MEASURED)
        phrase = (missing[0] if len(missing) == 1
                  else ", ".join(missing[:-1]) + " or " + missing[-1])
        st.caption("This device does not measure %s, so those charts are not "
                   "produced." % phrase)

    # --- suggestions, computed once per file ------------------------------
    sig = (name, len(data), device)
    if st.session_state.get("_sig") != sig:
        with st.spinner("Reading the file…"):
            _, suggestions, df = analysis.suggest_settings(data, name, device)
        st.session_state._sig = sig
        st.session_state.suggestions = suggestions
        st.session_state.dataframe = df
    suggestions = st.session_state.suggestions

    # --- irradiation ------------------------------------------------------
    st.subheader("Irradiation file")
    st.caption("A bundled profile is used unless you upload your own. "
               "Uploading one always wins.")
    c1, c2 = st.columns([2, 3])
    with c1:
        bundled = st.selectbox("Bundled profile", list(BUNDLED_IRRADIATION))
    with c2:
        irr_upload = st.file_uploader(
            "Or upload a different irradiation CSV",
            type=["csv", "txt"], key="irr")

    if irr_upload is not None:
        st.session_state.irradiation = (irr_upload.name, irr_upload.getvalue())
        st.success("Using your uploaded file: **%s**" % irr_upload.name)
    else:
        path = BUNDLED_IRRADIATION[bundled]
        if not os.path.exists(path):
            st.error("Bundled profile %s is missing from the repository."
                     % path)
            st.stop()
        with open(path, "rb") as fh:
            st.session_state.irradiation = (os.path.basename(path), fh.read())
        st.caption("Using the bundled **%s** profile. Upload a file above to "
                   "override it." % bundled)

    # --- plant details ----------------------------------------------------
    st.subheader("Customer and project")
    d1, d2, d3 = st.columns(3)
    with d1:
        customer = st.text_input("Customer name", value="Customer",
                                 help="Every chart title and every filename.")
    with d2:
        location = st.text_input("Site or location",
                                 help="Report metadata only. Not used in any "
                                      "calculation.")
    with d3:
        project_ref = st.text_input("Project reference",
                                    help="Report metadata only.")

    # --- analysis settings ------------------------------------------------
    st.subheader("Analysis settings")
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        rate = st.number_input("Sample rate [min]", min_value=1, step=1,
                               value=int(suggestions.get("RateMin", 1)),
                               help="Read from the timestamps.")
    with e2:
        delta = st.number_input("Time offset [h]", value=0, step=1,
                                help="+1 if the logger clock ran an hour "
                                     "behind.")
    with e3:
        default_unit = 0 if suggestions.get("Yformat", 1.0) == 1.0 else 1
        unit = st.selectbox("Power unit on the axis", ["kW", "W"],
                            index=default_unit,
                            help="Econ files are in kW; Shelly power is "
                                 "derived in W.")
    with e4:
        st.caption("Restrict the period")
        use_range = st.checkbox("Use a date range")

    date_from = date_to = None
    if use_range:
        v = st.session_state.dataframe
        f1, f2 = st.columns(2)
        with f1:
            date_from = st.date_input("From", value=None)
        with f2:
            date_to = st.date_input("To", value=None)
        st.caption("Rows outside the range are excluded from this analysis "
                   "only. Your file is not modified.")

    st.subheader("Proposed system sizes")
    g1, g2, g3 = st.columns([3, 1, 1])
    with g1:
        default_ppv = ", ".join(
            str(s) for s in cfg.DEVICE_DEFAULTS[device]["PPV"])
        sizes_text = st.text_input("Sizes to simulate [kWp]",
                                   value=default_ppv,
                                   help="Comma separated. Any number of "
                                        "sizes.")
    with g2:
        eta = st.number_input("EtaPV", min_value=0.05, max_value=1.0,
                              value=0.80, step=0.01, format="%.2f",
                              help="Total efficiency, PV rated to AC out.")
    with g3:
        offset = st.number_input("Offset", min_value=0.0, max_value=0.9,
                                 value=0.0, step=0.05, format="%.2f",
                                 help="0.1 keeps simulated generation 10% "
                                      "below consumption.")

    try:
        ppv = [int(round(float(p))) for p in sizes_text.replace(";", ",")
               .split(",") if p.strip()]
    except ValueError:
        st.error("System sizes must be numbers, comma separated.")
        st.stop()
    if not ppv:
        st.error("Enter at least one system size.")
        st.stop()

    # --- axes -------------------------------------------------------------
    with st.expander("Axis ranges — filled in from your file, open to override"):
        if suggestions:
            st.caption("Proposed from the uploaded data: "
                       + ", ".join("%s = %s" % kv
                                   for kv in sorted(suggestions.items())))
        conf = cfg.AnalysisConfig(device=device)
        for key, value in suggestions.items():
            if hasattr(conf, key):
                setattr(conf, key, value)

        a1, a2, a3 = st.columns(3)
        with a1:
            st.markdown("**Power**")
            conf.Ymin = st.number_input("Ymin", value=float(conf.Ymin))
            conf.Ymax = st.number_input("Ymax", value=float(conf.Ymax))
            conf.Ydist = st.number_input("Y tick spacing",
                                         value=float(conf.Ydist), min_value=0.001)
            st.markdown("**Voltage [V]**")
            conf.Umin = st.number_input("Umin", value=float(conf.Umin))
            conf.Umax = st.number_input("Umax", value=float(conf.Umax))
            conf.Udist = st.number_input("U tick spacing",
                                         value=float(conf.Udist), min_value=0.001)
        with a2:
            st.markdown("**Current [A]**")
            conf.Imin = st.number_input("Imin", value=float(conf.Imin))
            conf.Imax = st.number_input("Imax", value=float(conf.Imax))
            conf.Idist = st.number_input("I tick spacing",
                                         value=float(conf.Idist), min_value=0.001)
            st.markdown("**Power factor [-]**")
            conf.PFmin = st.number_input("PF min", value=float(conf.PFmin))
            conf.PFmax = st.number_input("PF max", value=float(conf.PFmax))
            conf.PFdist = st.number_input("PF tick spacing",
                                          value=float(conf.PFdist), min_value=0.001)
        with a3:
            if device == "econ":
                st.markdown("**Voltage THD [%]**")
                conf.THDmin = st.number_input("THD min", value=float(conf.THDmin))
                conf.THDmax = st.number_input("THD max", value=float(conf.THDmax))
                conf.THDdist = st.number_input("THD tick spacing",
                                               value=float(conf.THDdist),
                                               min_value=0.001)
                st.markdown("**Frequency [Hz]**")
                conf.Fmin = st.number_input("F min", value=float(conf.Fmin))
                conf.Fmax = st.number_input("F max", value=float(conf.Fmax))
                conf.Fdist = st.number_input("F tick spacing",
                                             value=float(conf.Fdist),
                                             min_value=0.001)
            else:
                st.markdown("**Apparent power [VA]**")
                conf.Amax = st.number_input("Apparent max", value=float(conf.Amax))
                conf.Adist = st.number_input("Apparent tick spacing",
                                             value=float(conf.Adist),
                                             min_value=0.001)

    conf.device = device
    conf.customer = customer or "Customer"
    conf.location = location
    conf.project_reference = project_ref
    conf.RateMin = int(rate)
    conf.deltatime = int(delta)
    conf.Yformat = 1.0 if unit == "kW" else 1e-3
    conf.PPV = ppv
    conf.EtaPV = float(eta)
    conf.Offset = float(offset)
    conf.date_from = date_from
    conf.date_to = date_to
    st.session_state.analysis_config = conf

    st.divider()
    st.button("Check the data →", type="primary",
              on_click=goto, args=(PAGES[2],), use_container_width=True)


# ===========================================================================
# 3 · DATA VALIDATION
# ===========================================================================

elif page == PAGES[2]:
    st.title("Data validation")

    conf = st.session_state.get("analysis_config")
    df = st.session_state.dataframe
    profile = st.session_state.profile
    if conf is None or df is None:
        st.info("Upload a file on page 2 first.")
        st.stop()

    with st.spinner("Checking…"):
        report = validation_mod.validate(df, conf.device,
                                         rate_min=conf.RateMin)
    st.session_state.validation = report

    st.subheader("File")
    c = st.columns(4)
    c[0].metric("Rows", "{:,}".format(report.n_rows))
    c[1].metric("Columns", report.n_columns)
    c[2].metric("Separator", "'%s'" % profile.delimiter)
    c[3].metric("Encoding", profile.encoding)

    st.subheader("Measurement period")
    c = st.columns(4)
    c[0].metric("From", str(report.first_timestamp)[:16])
    c[1].metric("To", str(report.last_timestamp)[:16])
    c[2].metric("Span", "%.1f days" % report.span_days)
    c[3].metric("Recorded", "%.0f%%" % (100 * report.overall_coverage))
    if report.overall_coverage < cfg.MIN_OVERALL_COVERAGE:
        c[3].caption("below the %.0f%% this tool expects"
                     % (100 * cfg.MIN_OVERALL_COVERAGE))

    # --- findings ---------------------------------------------------------
    st.subheader("Findings")
    if not report.issues:
        st.success("No problems found.")
    for issue in report.issues:
        text = "**%s** — %s" % (issue.title, issue.detail) if issue.detail \
            else "**%s**" % issue.title
        {"error": st.error, "warning": st.warning,
         "info": st.info}[issue.severity](text)

    # --- coverage ---------------------------------------------------------
    st.subheader("Coverage")
    st.caption("How much of each period was actually recorded. A tariff "
               "window below %.0f%% is reported as “not measured” rather "
               "than as a number." % (100 * cfg.MIN_WINDOW_COVERAGE))
    w1, w2 = st.columns([1, 2])
    with w1:
        st.dataframe(pd.DataFrame(
            [{"Window": w, "Coverage %": round(100 * c, 1),
              "Reported as": ("not measured"
                              if c < cfg.MIN_WINDOW_COVERAGE else "a number")}
             for w, c in report.window_coverage.items()]),
            hide_index=True, use_container_width=True)
    with w2:
        st.bar_chart(validation_mod.coverage_frame(report)
                     .set_index("Hour")["Coverage %"], height=220)

    with st.expander("Coverage by day"):
        st.dataframe(validation_mod.day_frame(report), hide_index=True,
                     use_container_width=True)
    if report.gaps:
        with st.expander("Largest gaps (%d in total)" % len(report.gaps)):
            st.dataframe(pd.DataFrame(
                [{"From": str(a)[:16], "To": str(b)[:16],
                  "Hours": round(h, 1)} for a, b, h in report.gaps[:25]]),
                hide_index=True, use_container_width=True)

    with st.expander("Detected columns (%d)" % report.n_columns):
        required = set(fd.REQUIRED_COLUMNS[conf.device])
        st.dataframe(pd.DataFrame(
            [{"Column": c, "Used by the analysis": c in required}
             for c in df.columns]), hide_index=True, use_container_width=True)

    # --- run --------------------------------------------------------------
    st.divider()
    if not report.can_proceed:
        st.error("The analysis cannot run until the blocking issues above "
                 "are resolved.")
        st.stop()

    if report.warnings:
        st.checkbox("I have read the warnings above and want to continue",
                    key="ack_warnings")
        ready = st.session_state.get("ack_warnings", False)
    else:
        ready = True

    if st.button("Run the analysis", type="primary", disabled=not ready,
                 use_container_width=True):
        old = st.session_state.session_obj
        if old is not None:
            old.close()
        session = analysis.Session()
        st.session_state.session_obj = session

        bar = st.progress(0.0, text="Starting…")

        def on_progress(i, total, label):
            bar.progress(min(i / total, 1.0),
                         text="%d/%d · %s" % (min(i + 1, total), total, label))

        lock = run_lock()
        if not lock.acquire(blocking=False):
            with st.spinner("Another analysis is running — yours starts when "
                            "it finishes."):
                lock.acquire()
        try:
            with st.spinner("Drawing the figures. About a minute."):
                result = analysis.run(
                    conf,
                    st.session_state.measurement[1],
                    st.session_state.measurement[0],
                    st.session_state.irradiation[1],
                    st.session_state.irradiation[0],
                    session=session, progress=on_progress)
        finally:
            lock.release()
        bar.empty()
        st.session_state.result = result
        goto(PAGES[3])
        st.rerun()


# ===========================================================================
# 4 · ANALYSIS RESULTS
# ===========================================================================

elif page == PAGES[3]:
    st.title("Analysis results")
    result = st.session_state.result
    if result is None:
        st.info("Run the analysis on page 3 first.")
        st.stop()

    if result.errors:
        st.warning("%d step(s) did not finish." % len(result.errors))
        with st.expander("What went wrong"):
            for label, message in result.errors:
                st.markdown("**%s** — `%s`" % (label, message))
    else:
        st.success("%d figures produced with no errors." % len(result.figures))

    # --- summary tables ---------------------------------------------------
    st.subheader("Summary")
    t1, t2 = st.columns(2)
    with t1:
        st.markdown("**Electricity consumption**")
        st.dataframe(result.energy_summary_annotated,
                     use_container_width=True)
        if result.validation and result.validation.unmeasured_windows:
            st.caption("“not measured” means the meter recorded almost "
                       "nothing in that window. The original code reports "
                       "0 kWh there, which reads as a measured zero.")
    with t2:
        st.markdown("**Maximum PV yield**")
        st.dataframe(result.pv_yield, use_container_width=True)

    if result.pv_detail is not None and not result.pv_detail.empty:
        st.markdown("**Direct PV consumption and share**")
        st.dataframe(result.pv_detail, use_container_width=True)

    # --- sizing -----------------------------------------------------------
    st.subheader("Proposed system sizes")
    s = result.sizing
    if s is None or not s.assessments:
        st.info("No candidate sizes could be assessed.")
    else:
        st.warning("**Preliminary — requires engineering review.** "
                   + sizing_mod.headline(s), icon="⚠")
        st.dataframe(s.table, hide_index=True, use_container_width=True)

        st.markdown("**Why each size ranks where it does**")
        for a in s.assessments:
            with st.expander("%g kWp — %s" % (a.kwp, a.verdict)):
                for reason in a.reasons:
                    st.markdown("- " + reason)

        b1, b2 = st.columns(2)
        with b1:
            st.markdown("**Calculated from your data**")
            st.dataframe(pd.DataFrame(
                [{"Item": k, "Value": v} for k, v in s.measured_inputs.items()]),
                hide_index=True, use_container_width=True)
        with b2:
            st.markdown("**Assumptions you entered**")
            st.dataframe(pd.DataFrame(
                [{"Item": k, "Value": v}
                 for k, v in s.user_assumptions.items()]),
                hide_index=True, use_container_width=True)

        st.markdown("**Caveats**")
        for caveat in s.caveats:
            st.markdown("- " + caveat)

    # --- figures ----------------------------------------------------------
    st.subheader("Figures")
    groups = {}
    for path in result.figures:
        head = os.path.basename(path).split(" ")[0]
        groups.setdefault(head.split(".")[0], []).append(path)
    for key in sorted(groups, key=lambda k: (len(k), k)):
        files = sorted(groups[key])
        with st.expander("Section %s (%d)" % (key, len(files))):
            for path in files:
                st.markdown("`%s`" % os.path.basename(path))
                st.image(path, use_container_width=True)

    st.divider()
    st.button("Downloads →", type="primary", on_click=goto, args=(PAGES[4],))


# ===========================================================================
# 5 · DOWNLOADS
# ===========================================================================

elif page == PAGES[4]:
    st.title("Downloads")
    result = st.session_state.result
    if result is None:
        st.info("Run the analysis on page 3 first.")
        st.stop()

    stamp = datetime.now().strftime("%Y-%m-%d")
    base = "%s %s" % (result.config.customer, stamp)

    st.subheader("Everything")
    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button("All figures (ZIP)",
                           data=reporting.build_zip(result),
                           file_name="%s graphs.zip" % base,
                           mime="application/zip",
                           use_container_width=True)
        st.caption("%d figures plus the settings used." % len(result.figures))
    with d2:
        st.download_button("Summary (XLSX)",
                           data=reporting.build_xlsx(result),
                           file_name="%s summary.xlsx" % base,
                           mime="application/vnd.openxmlformats-officedocument"
                                ".spreadsheetml.sheet",
                           use_container_width=True)
        st.caption("Tables, validation findings, coverage and settings.")
    with d3:
        if st.button("Build the PDF report", use_container_width=True):
            with st.spinner("Building…"):
                st.session_state.pdf = reporting.build_pdf(result)
        if st.session_state.get("pdf"):
            st.download_button("Report (PDF)", data=st.session_state.pdf,
                               file_name="%s report.pdf" % base,
                               mime="application/pdf",
                               use_container_width=True)
        st.caption("Cover, basis, caveats and every figure.")

    if result.data_files:
        st.subheader("Data exports")
        for path in result.data_files:
            with open(path, "rb") as fh:
                st.download_button(os.path.basename(path), data=fh.read(),
                                   file_name=os.path.basename(path),
                                   mime="text/csv")

    st.subheader("Individual figures")
    for path in result.figures:
        c1, c2 = st.columns([4, 1])
        c1.markdown("`%s`" % os.path.basename(path))
        with open(path, "rb") as fh:
            c2.download_button("Download", data=fh.read(),
                               file_name=os.path.basename(path),
                               mime="image/png", key=path)

    st.divider()
    if st.button("Clear this analysis and delete its temporary files"):
        session = st.session_state.session_obj
        if session is not None:
            session.close()
        for key in ("result", "session_obj", "pdf", "validation",
                    "measurement", "profile", "dataframe", "_sig"):
            st.session_state.pop(key, None)
        goto(PAGES[0])
        st.rerun()
