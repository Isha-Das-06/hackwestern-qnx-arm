@echo off
rem Start the app on the laptop (same Python code as the Pi). First run sets everything up (a few minutes).
rem Extra options pass through, e.g.  run_python.bat --cam 1
cd /d "%~dp0"
if not exist python\.venv\Scripts\python.exe (
  echo Setting up Python environment...
  py -3.12 -m venv python\.venv || exit /b 1
  python\.venv\Scripts\python -m pip install -r python\requirements.txt || exit /b 1
)
if not exist models\hand_landmarker.task (
  echo Downloading hand model...
  curl -sSfL -o models\hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task || exit /b 1
)
python\.venv\Scripts\python python\pointing.py %*
