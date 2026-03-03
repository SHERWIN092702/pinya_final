# app.py with results pie chart using detection count file (RTMP/Phone only)

import streamlit as st
import subprocess
import sys
import time
import json
from pathlib import Path
import plotly.graph_objects as go

DETECTION_SCRIPT = r"C:\Users\Acer\Desktop\Thesis\model11.py"
COUNTS_FILE = Path(r"C:\Users\Acer\Desktop\Thesis\detectioncount\detection_counts.json")

# ─────────────────────────  CSS  ──────────────────────────
st.markdown("""
<style>
.stApp {
    background-image: url("https://github.com/SHERWIN092702/pineapple-drone-app/blob/main/background.jpg?raw=true");
    background-size: cover; background-position: center;
    background-attachment: fixed; background-repeat: no-repeat;
}
.overlay {
    background:rgba(0,0,0,.6);padding:40px;border-radius:12px;
    color:#fff;margin:40px auto;max-width:800px;text-align:center;
}
</style>
""", unsafe_allow_html=True)

# ──────────────────  Session State  ───────────────────────
if 'page' not in st.session_state: st.session_state.page = 'home'
if 'proc' not in st.session_state: st.session_state.proc = None
if 'stream_mode' not in st.session_state: st.session_state.stream_mode = 'RTMP Stream'
if 'stream_path' not in st.session_state: st.session_state.stream_path = ''
if 'scrcpy_proc' not in st.session_state: st.session_state.scrcpy_proc = None

# ═══════════════════  Pages  ══════════════════════════════
def home_page():
    st.markdown("<div class='overlay'><h1>Drone Pineapple Maturity Detection</h1></div>", unsafe_allow_html=True)
    if st.button("🔌 Connect", use_container_width=True):
        st.session_state.page = 'about'

def about_page():
    st.markdown("<div class='overlay'><h2>HOW IT WORKS</h2></div>", unsafe_allow_html=True)
    steps = [
        "1. Choose a video source (RTMP or Phone Capture).",
        "2. Paste the stream URL if required.",
        "3. Press START to begin detection.",
        "4. View live bounding-box window + dashboard counts.",
        "5. Press RESULTS for the pie chart or EXIT to quit."
    ]
    for s in steps: st.markdown(f"<p style='color:white'>{s}</p>", unsafe_allow_html=True)
    if st.button("🚀 START", use_container_width=True):
        st.session_state.page = 'control'

def control_panel():
    st.markdown("<div class='overlay'><h2>CONTROL PANEL</h2></div>", unsafe_allow_html=True)

    # Source selector
    source_options = ["RTMP Stream", "Phone Capture (scrcpy)"]
    st.session_state.stream_mode = st.selectbox("Select Video Source:", source_options)

    # URL input for RTMP
    if st.session_state.stream_mode == "RTMP Stream":
        st.session_state.stream_path = st.text_input("📺 Stream URL:", value=st.session_state.stream_path)

    # Buttons layout
    col1, col2 = st.columns(2)

    # ── START DETECTION ──
    with col1:
        if st.button("📷 START DETECTION", use_container_width=True):
            src_map = {
                "Phone Capture (scrcpy)": "scrcpy",
                "RTMP Stream": "RTMP",
            }
            src_flag = src_map[st.session_state.stream_mode]

            # Validate RTMP URL
            if src_flag == "RTMP":
                url = st.session_state.stream_path.strip()
                if not url.startswith("rtmp://"):
                    st.error("❌ RTMP links must start with rtmp://")
                    return

            # Launch scrcpy if needed
            if src_flag == "scrcpy":
                bat_file = r"C:\Users\Acer\Desktop\Thesis\scrcpy_start.bat"
                if st.session_state.scrcpy_proc is None:
                    try:
                        st.session_state.scrcpy_proc = subprocess.Popen([bat_file], shell=True)
                        st.success("📱 Phone mirroring launched.")
                        time.sleep(1)  # Give scrcpy a moment to open
                    except Exception as e:
                        st.error(f"❌ Failed to launch scrcpy: {e}")
                        return

            # Terminate previous detection process if exists
            if st.session_state.proc:
                st.session_state.proc.terminate()
                st.session_state.proc = None

            # Build detection arguments
            args = [sys.executable, DETECTION_SCRIPT, "--source", src_flag]
            if src_flag == "RTMP":
                args += ["--url", st.session_state.stream_path.strip()]

            try:
                st.session_state.proc = subprocess.Popen(args)
                st.success("✅ Detection started.")
            except Exception as e:
                st.error(f"❌ Failed to start detection: {e}")

    # ── STOP DETECTION ──
    with col2:
        if st.button("🔴 STOP", use_container_width=True):
            # Stop detection process
            if st.session_state.proc:
                st.session_state.proc.terminate()
                st.session_state.proc = None
            # Stop scrcpy if running
            if st.session_state.scrcpy_proc:
                st.session_state.scrcpy_proc.terminate()
                st.session_state.scrcpy_proc = None
            st.success("🛑 Detection stopped.")

    # ── RESULTS / BACK ──
    col3, col4 = st.columns(2)
    with col3:
        if st.button("📊 RESULTS", use_container_width=True):
            st.session_state.page = 'results'
    with col4:
        if st.button("⬅️ EXIT TO HOME", use_container_width=True):
            # Ensure all processes are stopped when leaving
            if st.session_state.proc:
                st.session_state.proc.terminate()
                st.session_state.proc = None
            if st.session_state.scrcpy_proc:
                st.session_state.scrcpy_proc.terminate()
                st.session_state.scrcpy_proc = None
            st.session_state.page = 'home'

def results_page():
    st.markdown("<div class='overlay'><h2>DETECTION RESULTS</h2></div>", unsafe_allow_html=True)

    counts = {"ripe": 0, "unripe": 0, "overripe": 0}
    if COUNTS_FILE.exists():
        counts = json.load(COUNTS_FILE.open())

    total = sum(counts.values())

    if total == 0:
        st.warning("No detection data yet. Run detection first.")
    else:
        ripe_pct = (counts["ripe"] / total) * 100
        unripe_pct = (counts["unripe"] / total) * 100
        overripe_pct = (counts["overripe"] / total) * 100

        col_l, _, col_r = st.columns([1, 0.3, 1])

        with col_l:
            st.markdown(f"""
<div style='background:#2e2e2e;padding:20px 30px;border-radius:12px;color:#fff'>
<h3>🍍 Maturity Breakdown</h3>
<p><span style='color:limegreen'>🟢 Ripe:</span> {ripe_pct:.1f}%</p>
<p><span style='color:orange'>🟠 Unripe:</span> {unripe_pct:.1f}%</p>
<p><span style='color:crimson'>🔴 Overripe:</span> {overripe_pct:.1f}%</p>
</div>""", unsafe_allow_html=True)

        with col_r:
            fig = go.Figure(go.Pie(
                labels=["Ripe", "Unripe", "Overripe"],
                values=[counts["ripe"], counts["unripe"], counts["overripe"]],
                hole=0.3,
                marker=dict(colors=["limegreen", "orange", "crimson"]),
                textinfo="label+percent"
            ))
            fig.update_layout(
                showlegend=False,
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=0, b=0),
                height=300,
                width=300,
                font=dict(color="white")
            )
            st.plotly_chart(fig, use_container_width=False)

    col_reset, col_back = st.columns(2)
    with col_reset:
        if st.button("🔄 RESET DATA", use_container_width=True):
            try:
                with COUNTS_FILE.open("w") as f:
                    json.dump({"ripe": 0, "unripe": 0, "overripe": 0}, f)
                st.success("✅ Detection data reset.")
                st.rerun()
            except Exception as e:
                st.error(f"⚠️ Failed to reset data: {e}")

    with col_back:
        if st.button("⬅️ BACK TO CONTROL", use_container_width=True):
            st.session_state.page = 'control'

# ──────────────────  Router ──────────────────────────────
if st.session_state.page == 'home': home_page()
elif st.session_state.page == 'about': about_page()
elif st.session_state.page == 'control': control_panel()
elif st.session_state.page == 'results': results_page()
