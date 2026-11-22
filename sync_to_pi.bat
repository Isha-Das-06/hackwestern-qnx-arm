@echo off
rem Copy the robot code to the QNX Pi in one go: the arm side (mks_servo\ -> ~/mks_servo)
rem and the vision side (python\, qnx\, run_pi.sh -> ~/pickvision).
rem The Pi keeps its own taught data, because it belongs to that camera and that arm:
rem   ~/pickvision/config (pocket boxes + classifier examples), ~/mks_servo/config/taught.json
rem Uses the pickvision_pi SSH key if this laptop has it; otherwise ssh asks for the password.
cd /d "%~dp0"
set PI=qnxuser@192.168.8.247
set K=-o LogLevel=ERROR -o ConnectTimeout=10 -c aes128-ctr -o MACs=hmac-sha2-256
if exist "%USERPROFILE%\.ssh\pickvision_pi" set K=%K% -i "%USERPROFILE%\.ssh\pickvision_pi"

echo Copying code to the Pi...
rem One tar stream into a staging folder, then each part goes where it lives on the Pi.
tar -cf - --exclude=__pycache__ --exclude=.venv --exclude=mks_servo/config/taught.json ^
    mks_servo python qnx/pv_cam.c qnx/Makefile run_pi.sh ^
  | ssh %K% %PI% "S=~/.sync_stage; rm -rf $S && mkdir -p $S ~/pickvision && tar -xf - -C $S && cd $S && cp -R mks_servo ~/ && cp -R python qnx run_pi.sh ~/pickvision/ && cd ~ && rm -rf $S && chmod +x ~/mks_servo/*.sh ~/pickvision/run_pi.sh && make -s -C ~/pickvision/qnx" || goto fail

rem The full robot starts vision itself (supervisor). Only restart the stand-alone vision app.
ssh %K% %PI% "pidin -f aA | grep -q '[p]ython3 supervisor.py'" && (
    echo.
    echo The robot is running. Restart it to load the new code:  ~/mks_servo/start_robot.sh
    pause
    exit /b 0
)
ssh %K% %PI% "cd ~/pickvision && ./run_pi.sh stop" || goto fail
ssh -f %K% %PI% "cd ~/pickvision && nohup ./run_pi.sh > pointing.log 2>&1 < /dev/null &" || goto fail

echo.
echo Done. Give it ~10 seconds, then open  http://192.168.8.247:8080
echo Whole robot instead:  ssh in, then  ~/mks_servo/start_robot.sh   (dashboard on port 8090)
pause
exit /b 0

:fail
echo.
echo FAILED - is the Pi on, and is your laptop on the same Wi-Fi?
pause
exit /b 1
