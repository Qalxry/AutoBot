if command -v xfce4-terminal >/dev/null 2>&1; then
    xfce4-terminal --title="AutoBot_Terminal" --command="bash ./scripts/adjust_terminal.sh"
elif command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal --title="AutoBot_Terminal" --command="bash ./scripts/adjust_terminal.sh"
elif command -v xterm >/dev/null 2>&1; then
    xterm -T "AutoBot_Terminal" -e "bash ./scripts/adjust_terminal.sh"
else
    echo "[AutoBot] xfce4-terminal or gnome-terminal not found, please install one of them."
fi