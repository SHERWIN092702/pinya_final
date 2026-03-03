@echo off
REM ── Launch Streamlit app on all interfaces but hide default browser ──
start "" python -m streamlit run "C:\Users\Acer\Desktop\Thesis\app.py" --server.address=0.0.0.0 --server.headless true

REM ── Wait a few seconds for Streamlit to start ──
timeout /t 5 /nobreak > nul

REM ── Get LAN IP of this PC ──
for /f "tokens=14 delims= " %%a in ('ipconfig ^| findstr /R "IPv4"') do set ip=%%a
echo Detected LAN IP: %ip%

REM ── Open default browser with the correct Streamlit URL ──
start "" http://%ip%:8501

pause
