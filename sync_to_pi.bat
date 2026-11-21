@echo off
rem Copy the CODE (not the training/pocket files) to the QNX Pi and restart the app there.
rem The Pi keeps its own config\tray.yml and config\classifier_py.npz, because those
rem belong to the Pi's camera. Needs the SSH key set up earlier (pickvision_pi).
cd /d "%~dp0"
set PI=qnxuser@192.168.8.247
set K=-i "%USERPROFILE%\.ssh\pickvision_pi" -o BatchMode=yes -o LogLevel=ERROR -o ConnectTimeout=10 -c aes128-ctr -o MACs=hmac-sha2-256

echo Copying code to the Pi...
scp %K% python\classifier.py python\logic.py python\pointing.py python\handtrack_tflite.py python\qnx_camera.py python\web_ui.py python\pi_test.py %PI%:pickvision/python/ || goto fail
scp %K% -r python\web %PI%:pickvision/python/ || goto fail
scp %K% qnx\pv_cam.c qnx\Makefile %PI%:pickvision/qnx/ || goto fail
scp %K% run_pi.sh %PI%:pickvision/ || goto fail

echo Rebuilding the camera bridge and restarting the app on the Pi...
ssh %K% %PI% "cd ~/pickvision && chmod +x run_pi.sh && ./run_pi.sh stop && make -s -C qnx" || goto fail
ssh -f %K% %PI% "cd ~/pickvision && nohup ./run_pi.sh > pointing.log 2>&1 < /dev/null &" || goto fail

echo.
echo Done. Give it ~10 seconds, then open  http://192.168.8.247:8080
pause
exit /b 0

:fail
echo.
echo FAILED - is the Pi on, and is your laptop on the same Wi-Fi?
pause
exit /b 1
