#!/bin/sh
# Bring up UART3 + UART5 (the two SERVO42C drivers) and UART4 (Pico 2 gripper
# board). Run as root.
# Safe to run more than once. To run at boot, add this to
# /usr/etc/startup/post_startup.sh:  sh /data/home/qnxuser/mks_servo/uart_setup.sh
#
#   UART3  /dev/ser3  GPIO4 TX (pin 7)   GPIO5 RX (pin 29)   -> motor 1
#   UART5  /dev/ser5  GPIO12 TX (pin 32) GPIO13 RX (pin 33)  -> motor 2
#   UART4  /dev/ser4  GPIO8 TX (pin 24)  GPIO9 RX (pin 21)   -> Pico 2 gripper
#
# GPIO8/9 are SPI0 pins too. Nothing on this robot uses SPI0, so we take them
# over for UART4 (alt function 4). spi-bcm2711 still starts at boot; harmless.
#
# -c48000000: the Pi 4 UART clock measures 48 MHz (vcgencmd measure_clock uart).
# QNX's guide shows 50 MHz, which would put the baud rate ~4% off.

command -v devc-serpl011 >/dev/null || { echo "missing devc-serpl011: apk add qnx-devc"; exit 1; }

start_uart() {  # unit tx rx base
    gpio-bcm2711 set $2,$3 a4
    gpio-bcm2711 set $3 pu          # idle-high RX so a loose wire doesn't read as noise
    if [ -e /dev/ser$1 ]; then
        echo "/dev/ser$1 already running"
    else
        devc-serpl011 -b115200 -c48000000 -e -F -u$1 $4,153 </dev/null >/dev/null 2>&1
        sleep 1
    fi
    [ -e /dev/ser$1 ] && stty baud=115200 par=none bits=8 stopb=1 < /dev/ser$1
    [ -e /dev/ser$1 ] && echo "/dev/ser$1 ready" || echo "/dev/ser$1 FAILED"
}

start_uart 3 4 5 0xfe201600
start_uart 5 12 13 0xfe201a00
start_uart 4 8 9 0xfe201800
