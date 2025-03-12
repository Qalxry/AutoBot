# Description: This script is used to start the AutoBot in Docker.
echo "[AutoBot] Configuring VNC..."
nohup "/dockerstartup/kasm_default_profile.sh" "/dockerstartup/vnc_startup.sh" "/dockerstartup/kasm_startup.sh" --wait &

# Wait for VNC to start
sleep 5

# Start AutoBot
echo "[AutoBot] Starting AutoBot in Docker..."
bash "/AutoBot/scripts/run_qq.sh"
cd /AutoBot
bash "/AutoBot/scripts/run_terminal.sh"