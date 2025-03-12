sleep 0.2
window_id=$(xdotool search --name "AutoBot_Terminal")
sleep 0.2
xdotool windowactivate $window_id

read SCREEN_WIDTH SCREEN_HEIGHT <<< $(xdotool getdisplaygeometry)
HALF_WIDTH=$((SCREEN_WIDTH / 2))
FULL_HEIGHT=$SCREEN_HEIGHT
xdotool windowmove $window_id $HALF_WIDTH 0
xdotool windowsize $window_id $HALF_WIDTH $FULL_HEIGHT

# xdotool key super+Right # xdotool 发送 super+方向右键
# xdotool click --window "AutoBot_Terminal" 1
# sleep 0.2

echo "[AutoBot] Starting AutoBot..."
sleep 0.2
python3 main.py
