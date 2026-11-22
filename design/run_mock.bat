@echo off
rem Mock of the new console (no camera or robot needed). Then open http://localhost:8090
cd /d "%~dp0.."
echo Mock running. Open http://localhost:8090   (close this window to stop)
python\.venv\Scripts\python design\mock_server.py
