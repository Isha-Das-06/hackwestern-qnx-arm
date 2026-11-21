#!/bin/sh
# One-time setup of the PickVision history server on a fresh Vultr Ubuntu 22.04/24.04 server.
#
#   1. Copy the cloud/ folder to the server:   scp -r cloud root@<vultr-ip>:/root/
#   2. On the server:                          sh /root/cloud/setup_vultr.sh
#   3. It asks for the Tiger Data connection string, makes a token, and starts the service.
#
# Safe to run again (e.g. after copying a new version of server.py / dashboard.html).
set -e
APP=/opt/pickvision-cloud
ENVF=/etc/pickvision-cloud.env
SRC=$(cd "$(dirname "$0")" && pwd)

apt-get update -qq
apt-get install -y -qq python3-venv python3-pip >/dev/null

id pvcloud >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin pvcloud
mkdir -p "$APP"
cp "$SRC/server.py" "$SRC/dashboard.html" "$SRC/requirements.txt" "$APP/"
[ -d "$APP/.venv" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
chown -R pvcloud:pvcloud "$APP"

if [ ! -f "$ENVF" ]; then
    printf "Paste the Tiger Data connection string (postgres://...): "
    read -r DBURL
    TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
    umask 077
    printf 'DATABASE_URL=%s\nINGEST_TOKEN=%s\n' "$DBURL" "$TOKEN" > "$ENVF"
    chown root:pvcloud "$ENVF"; chmod 640 "$ENVF"
    echo "Saved to $ENVF"
fi

cat > /etc/systemd/system/pickvision-cloud.service <<EOF
[Unit]
Description=PickVision history (Tiger Data)
After=network-online.target
Wants=network-online.target

[Service]
User=pvcloud
EnvironmentFile=$ENVF
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 80 --proxy-headers
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable -q pickvision-cloud
systemctl restart pickvision-cloud
command -v ufw >/dev/null && ufw allow 80/tcp >/dev/null 2>&1 || true

sleep 3
IP=$(curl -s -4 https://ifconfig.me || hostname -I | awk '{print $1}')
if curl -sf http://127.0.0.1/healthz >/dev/null; then
    echo
    echo "Running.  Dashboard:  http://$IP/"
    echo "Put this in config/cloud.json on the Pi:"
    echo "  {\"url\": \"http://$IP\", \"token\": \"$(grep INGEST_TOKEN $ENVF | cut -d= -f2-)\"}"
else
    echo "Not running - see:  journalctl -u pickvision-cloud -n 40"
    exit 1
fi
