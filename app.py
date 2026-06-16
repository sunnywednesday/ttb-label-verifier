"""
TTB Label Verification Prototype

Built to spec from the discovery-session notes:
- 5-second-ish turnaround per label (Sarah's pilot-killer requirement)
- Large, obvious UI -- "my mother could figure it out" (Sarah)
- Batch upload for importer dumps of 200-300 labels (Sarah / Janet)
- Casing-tolerant matching on most fields (Dave's "Stone's Throw" case)
- Zero leniency on the Government Warning text (Jenny's example)
- No PII / nothing persisted to disk -- prototype only (Marcus's note)
"""

import io
import os
import sys
import zipfile

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(__file__))
from lib.extraction import extract_label_fields
from lib.matching import run_comparison, overall_status, MatchStatus

st.set_page_config(page_title="TTB Label Verification", layout="wide")

STATUS_COLOR = {
    MatchStatus.PASS: "#1a7f37",
    MatchStatus.REVIEW: "#9a6700",
    MatchStatus.FAIL: "#cf222e",
    MatchStatus.MISSING: "#cf222e",
}
STATUS_BG = {
    MatchStatus.PASS: "#dafbe1",
    MatchStatus.REVIEW: "#fff8c5",
    MatchStatus.FAIL: "#ffebe9",
    MatchStatus.MISSING: "#ffebe9",
}

st.markdown("""
<style>
    .big-title { font-size: 2.1rem; font-weight: 700; margin-bottom: 0; }
    .subtitle { font-size: 1.05rem; color: #57606a; margin-top: 0.2rem; }
    div[data-testid="stMetricValue"] { font-size: 1.7rem; }
    .status-pill {
        display: inline-block; padding: 6px 16px; border-radius: 20px;
        font-weight: 700; font-size: 1.1rem;
    }
    .field-row { padding: 10px 14px; border-radius: 8px; margin-bottom: 8px; }
    .field-name { font-weight: 700; font-size: 1.0rem; }
    .field-value { font-size: 0.95rem; }
    section[data-testid="stSidebar"] { width: 320px !important; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="big-title">TTB Label Verification</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Upload a label photo, compare it against the application, '
            'get a result in seconds.</p>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Setup")
    api_key = st.text_input("Anthropic API key", type="password",
                             value=os.environ.get("ANTHROPIC_API_KEY", ""),
                             help="Get one at console.anthropic.com. Not stored anywhere -- "
                                  "used only for this session's requests.")
    st.markdown("---")
    st.markdown("### About this prototype")
    st.caption(
        "Standalone proof-of-concept, not connected to COLA. Nothing you upload "
        "is saved to disk or a database -- it lives only in this browser session. "
        "Built for the take-home brief; see README for assumptions and trade-offs."
    )

mode = st.radio("Mode", ["Single Label", "Batch Upload"], horizontal=True, label_visibility="collapsed")

st.divider()


def render_results(results, latency=None, quality_issue=None):
    status = overall_status(results)
    colA, colB = st.columns([1, 3])
    with colA:
        st.markdown(
            f'<span class="status-pill" style="background:{STATUS_BG[status]};'
            f'color:{STATUS_COLOR[status]}">{status.value}</span>',
            unsafe_allow_html=True)
    with colB:
        if latency is not None:
            st.caption(f"Processed in {latency}s")
        if quality_issue:
            st.warning(f"Image quality note: {quality_issue}")

for r in results:
        note_html = (f'<br/><span class="field-value" style="font-style:italic">{r.note}</span>'
                     if r.note else "")
        row_html = (
            f'<div class="field-row" style="background:{STATUS_BG[r.status]}">'
            f'<span class="field-name" style="color:{STATUS_COLOR[r.status]}">{r.field} — {r.status.value}</span><br/>'
            f'<span class="field-value"><b>Application:</b> {r.application_value or "—"}</span><br/>'
            f'<span class="field-value"><b>On label:</b> {r.label_value or "(not found)"}</span>'
            f'{note_html}'
            f'</div>'
        )
        st.markdown(row_html, unsafe_allow_html=True)

if mode == "Single Label":
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 1. Application data")
        brand_name = st.text_input("Brand Name")
        class_type = st.text_input("Class / Type")
        abv = st.text_input("Alcohol Content (e.g. 45% Alc./Vol. (90 Proof))")
        net_contents = st.text_input("Net Contents (e.g. 750 mL)")
        producer = st.text_input("Name & Address of Bottler/Producer")
        country = st.text_input("Country of Origin (imports only, leave blank for domestic)")

    with col2:
        st.markdown("#### 2. Label photo")
        uploaded = st.file_uploader("Upload label image", type=["png", "jpg", "jpeg", "webp"])
        if uploaded:
            st.image(uploaded, caption="Label as submitted", width=320)

    if st.button("Verify Label", type="primary", use_container_width=True):
        if not api_key:
            st.error("Enter your Anthropic API key in the sidebar first.")
        elif not uploaded:
            st.error("Upload a label image first.")
        else:
            with st.spinner("Reading label..."):
                image_bytes = uploaded.getvalue()
                media_type = uploaded.type or "image/png"
                extracted = extract_label_fields(image_bytes, media_type, api_key)

            if extracted.get("_error"):
                st.error(f"Couldn't read this label: {extracted['_error']}")
            else:
                application = dict(brand_name=brand_name, class_type=class_type, abv=abv,
                                    net_contents=net_contents, producer_name_address=producer,
                                    country_of_origin=country)
                results = run_comparison(application, extracted)
                render_results(results, latency=extracted.get("_latency_seconds"),
                                quality_issue=extracted.get("image_quality_issue"))

else:
    st.markdown("#### Batch verification")
    st.caption(
        "Upload a CSV of application data and a ZIP of label images. The CSV needs an "
        "`image_filename` column matching each image's filename, plus the same fields as "
        "the single-label form. A sample is in `sample_data/applications.csv`."
    )
    c1, c2 = st.columns(2)
    with c1:
        csv_file = st.file_uploader("Application data (CSV)", type=["csv"])
    with c2:
        zip_file = st.file_uploader("Label images (ZIP)", type=["zip"])

    if st.button("Verify Batch", type="primary", use_container_width=True):
        if not api_key:
            st.error("Enter your Anthropic API key in the sidebar first.")
        elif not csv_file or not zip_file:
            st.error("Upload both the CSV and the ZIP of images.")
        else:
            df = pd.read_csv(csv_file)
            zf = zipfile.ZipFile(io.BytesIO(zip_file.getvalue()))
            progress = st.progress(0, text="Starting...")
            rows_out = []

            for i, row in df.iterrows():
                fname = row.get("image_filename", "")
                progress.progress((i + 1) / len(df), text=f"Processing {fname} ({i+1}/{len(df)})")
                try:
                    img_bytes = zf.read(fname)
                except KeyError:
                    rows_out.append({"image_filename": fname, "overall_status": "ERROR",
                                      "detail": "Image not found in ZIP."})
                    continue

                media_type = "image/png" if fname.lower().endswith("png") else "image/jpeg"
                extracted = extract_label_fields(img_bytes, media_type, api_key)
                if extracted.get("_error"):
                    rows_out.append({"image_filename": fname, "overall_status": "ERROR",
                                      "detail": extracted["_error"]})
                    continue

                application = {k: row.get(k, "") for k in
                                ["brand_name", "class_type", "abv", "net_contents",
                                 "producer_name_address", "country_of_origin"]}
                results = run_comparison(application, extracted)
                status = overall_status(results)
                failed_fields = [r.field for r in results if r.status != MatchStatus.PASS]
                rows_out.append({
                    "image_filename": fname,
                    "overall_status": status.value,
                    "flagged_fields": "; ".join(failed_fields) if failed_fields else "",
                    "latency_seconds": extracted.get("_latency_seconds"),
                    "image_quality_note": extracted.get("image_quality_issue", ""),
                })

            progress.empty()
            result_df = pd.DataFrame(rows_out)

            n_pass = (result_df["overall_status"] == "PASS").sum()
            n_review = (result_df["overall_status"] == "NEEDS REVIEW").sum()
            n_fail = (result_df["overall_status"].isin(["MISMATCH", "MISSING ON LABEL", "ERROR"])).sum()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total processed", len(result_df))
            m2.metric("Passed", int(n_pass))
            m3.metric("Needs review", int(n_review))
            m4.metric("Flagged / failed", int(n_fail))

            def _row_style(row):
                color = {"PASS": "#dafbe1", "NEEDS REVIEW": "#fff8c5"}.get(row["overall_status"], "#ffebe9")
                return [f"background-color: {color}"] * len(row)

            st.dataframe(result_df.style.apply(_row_style, axis=1), use_container_width=True, height=420)

            csv_bytes = result_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download results CSV", csv_bytes, "verification_results.csv", "text/csv")
