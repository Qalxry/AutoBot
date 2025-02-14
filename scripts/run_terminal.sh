sleep 0.2
window_id=$(xdotool search --name "AutoBot_Terminal")
sleep 0.2
xdotool windowactivate $window_id
sleep 0.2
xdotool key super+Right # xdotool 发送 super+方向右键
sleep 0.2
xdotool click --window "AutoBot_Terminal" 1
sleep 0.2
python3 main.py
