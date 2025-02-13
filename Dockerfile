# 使用官方Ubuntu Noble精简版基础镜像
FROM ubuntu:noble

# 安装核心组件并清理缓存（单层操作减少镜像体积）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    dbus \
    dbus-x11 \
    python3.10 \
    python3.10-venv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 创建VNC密码文件（密码为"autobot"）
RUN mkdir -p /root/.vnc && \
    x11vnc -storepasswd autobot /root/.vnc/passwd && \
    chmod 600 /root/.vnc/passwd

# 设置启动脚本
COPY start.sh /
RUN chmod +x /start.sh

# 暴露VNC端口
EXPOSE 5900

# 启动服务
CMD ["/start.sh"]
