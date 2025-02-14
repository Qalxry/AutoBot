import os
import shutil
import asyncio
from notify_auto import message_monitor, set_config, init_auto
from autobot_rws import run_reverse_websocket
from log_config import set_logger_level
import yaml

# TODO 使用 xdotool 获取 QQ 窗口句柄和位置，并自动定位
# TODO 自动爬取 QQ 群成员列表和 QQ 好友/群列表
# TODO 修复 jmcomic 的页面顺序问题
# TODO 部署到 VirtualBox 上 / 拥有 GUI 的 Docker 容器上
# TODO 开发 AstrBot 端的 LLM 智能聊天功能（回复 JSON 来控制附加功能）
# TODO 将 AutoBot 上传到 PyPI 上

async def main():
    if not os.path.exists("data/config.yaml"):
        shutil.copyfile("config.default.yaml", "data/config.yaml")
    
    with open("data/config.yaml", "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        
    # 清空临时文件夹
    clear_temp_at_startup = config.get("clear_temp_at_startup", True)
    if clear_temp_at_startup:
        TEMP_DIR = config["TEMP_DIR"]
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        os.makedirs(TEMP_DIR, exist_ok=True)
    
    set_logger_level(config["log_level"])
    set_config(config)
    init_auto()
    asyncio.create_task(message_monitor())
    await run_reverse_websocket(config["ws_server"], config["self_id"])


if __name__ == "__main__":
    asyncio.run(main())
