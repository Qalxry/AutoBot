# /bin/bash
# nohup "/AutoBot/scripts/run_vnc.sh" &

echo "\n[AutoBot] Starting AutoBot in Docker..."
# sleep 10
echo "\n[AutoBot] Going to start QQ..."
nohup /opt/QQ/qq --no-sandbox >/dev/null 2>&1 &
echo "\n[AutoBot] QQ started."

# sleep 3
# qq_login_window_id=$(xdotool search --onlyvisible --name "QQ")
# echo "\n[AutoBot] QQ login window id: $qq_login_window_id"
# xdotool windowactivate $qq_login_window_id
# sleep 0.1
# xdotool key Return
# sleep 0.1

# while true; do
#     sleep 0.1
#     now_qq_window_id=$(xdotool search --onlyvisible --name "QQ")
#     if [ "$now_qq_window_id" != "" ] && [ "$now_qq_window_id" != "$qq_login_window_id" ]; then

#         echo "\n[AutoBot] QQ main window started."
#         break
#     fi
# done
# echo "\n[AutoBot] QQ main window id: $now_qq_window_id"
# sleep 1
# xdotool windowactivate $now_qq_window_id
# sleep 0.2
# xdotool key super+Left
# sleep 0.2
# xdotool click --window "QQ" 1
# sleep 1
# echo "\n[AutoBot] QQ started."

# cd /AutoBot
# if command -v xfce4-terminal >/dev/null 2>&1; then
#     xfce4-terminal --title="AutoBot_Terminal" --command="bash ./scripts/run_terminal.sh"
# elif command -v gnome-terminal >/dev/null 2>&1; then
#     gnome-terminal --title="AutoBot_Terminal" --command="bash ./scripts/run_terminal.sh"
# elif command -v xterm >/dev/null 2>&1; then
#     xterm -T "AutoBot_Terminal" -e "bash ./scripts/run_terminal.sh"
# else
#     echo "\n[AutoBot] xfce4-terminal or gnome-terminal not found, please install one of them."
# fi
