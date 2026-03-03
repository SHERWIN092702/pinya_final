@echo off
REM ── Launch Streamlit app locally ──
start "" python -m streamlit run "C:\Users\Acer\Desktop\Thesis\app.py" --server.address=127.0.0.1 --server.headless true

REM ── Wait a few seconds for Streamlit to start ──
timeout /t 3 /nobreak > nul

REM ── Open default browser at localhost ──
start "" http://127.0.0.1:8501

pause
