# /bin/bash
# 检查是否已经启动 QQ
qq_pid=$(pgrep qq)
if [ "$qq_pid" != "" ]; then
    echo "[AutoBot] QQ is already running, please check."
    qq_window_id=$(xdotool search --onlyvisible --name "QQ")
    echo "[AutoBot] QQ window id: $qq_window_id"
    exit 0
else
    echo "[AutoBot] QQ is not running, going to start QQ..."
    nohup /opt/QQ/qq --no-sandbox >/dev/null 2>&1 &

    while true; do
        sleep 1
        qq_pid=$(pgrep qq)
        if [ "$qq_pid" != "" ]; then
            echo "[AutoBot] QQ started, pid: $qq_pid"
            break
        fi
    done
    sleep 2
    qq_login_window_id=$(xdotool search --onlyvisible --name "QQ")
    echo "[AutoBot] QQ login window id: $qq_login_window_id"
    xdotool key Return

    timeout=0
    while true; do
        sleep 1
        qq_window_id=$(xdotool search --onlyvisible --name "QQ")
        if [ "$qq_window_id" != "" ] && [ "$qq_window_id" != "$qq_login_window_id" ]; then
            echo "[AutoBot] QQ main window started: $qq_window_id"
            sleep 2
            break
        fi
        timeout=$((timeout + 1))
        if [ $timeout -gt 10 ]; then
            echo "[AutoBot] QQ main window not found, maybe you have not logged in."
        fi
    done
fi

# 计算左半屏参数
read SCREEN_WIDTH SCREEN_HEIGHT <<<$(xdotool getdisplaygeometry)
HALF_WIDTH=$((SCREEN_WIDTH / 2))
FULL_HEIGHT=$SCREEN_HEIGHT
xdotool windowmove "$qq_window_id" 0 0
xdotool windowsize "$qq_window_id" $HALF_WIDTH $FULL_HEIGHT

echo "[AutoBot] QQ started."
