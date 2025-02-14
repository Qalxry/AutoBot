import os
import re
import random
import time
import asyncio
import pyautogui
import pyperclip
import subprocess
import tui
import atexit
import imghdr
import pybase64
import mimetypes
import magic
import shutil
from log_config import logger
from typing import Literal, Optional

# 等待时间
WAIT_TIME = 0.5
SMALL_WAIT_TIME = 0.05
LOCATE_METHOD = "absolute"
SCREEN_SIZE = pyautogui.size()
QQ_WINDOW_POS = (640, 800)
QQ_INPUT_POS = (862, 1455)
OTHER_WINDOW_POS = (1960, 800)
TEMP_DIR = "./temp"
ASTRBOT_DATA_DIR = "./"
NOTIFICATION_REPEAT_COUNT = 2

# 聊天信息
self_id = 1950154414
self_name = "Vanilla"
chat_info = {
    "1033991906": {
        "chat_name": "QQ群的群名称",
        "chat_type": "group",
    },
    "1029169577": {
        "chat_name": "ShizuriYuki",
        "chat_type": "private",
    },
}


# configs.yaml
def create_mapping(chat_info):
    chat_id2chat_name = {k: v["chat_name"] for k, v in chat_info.items()}
    chat_name2chat_type = {v["chat_name"]: v["chat_type"] for v in chat_info.values()}
    chat_name2chat_id = {v: k for k, v in chat_id2chat_name.items()}
    chat_id2chat_type = {k: chat_name2chat_type[v] for k, v in chat_id2chat_name.items()}
    return chat_id2chat_name, chat_name2chat_type, chat_name2chat_id, chat_id2chat_type


def set_config(config: dict):
    global self_id, self_name, chat_info
    global WAIT_TIME, SMALL_WAIT_TIME, TEMP_DIR, ASTRBOT_DATA_DIR
    global QQ_WINDOW_POS, QQ_INPUT_POS, OTHER_WINDOW_POS, LOCATE_METHOD, NOTIFICATION_REPEAT_COUNT
    global chat_id2chat_name, chat_name2chat_type, chat_name2chat_id, chat_id2chat_type
    self_id = config.get("self_id", self_id)
    self_name = config.get("self_name", self_name)
    chat_info = config.get("chat_info", chat_info)
    WAIT_TIME = config.get("WAIT_TIME", WAIT_TIME)
    SMALL_WAIT_TIME = config.get("SMALL_WAIT_TIME", SMALL_WAIT_TIME)
    LOCATE_METHOD = config.get("LOCATE_METHOD", LOCATE_METHOD)
    QQ_WINDOW_POS = config.get("QQ_WINDOW_POS", QQ_WINDOW_POS)
    QQ_INPUT_POS = config.get("QQ_INPUT_POS", QQ_INPUT_POS)
    OTHER_WINDOW_POS = config.get("OTHER_WINDOW_POS", OTHER_WINDOW_POS)
    if LOCATE_METHOD == "relative":
        QQ_WINDOW_POS = (int(SCREEN_SIZE.width * QQ_WINDOW_POS[0]), int(SCREEN_SIZE.height * QQ_WINDOW_POS[1]))
        QQ_INPUT_POS = (int(SCREEN_SIZE.width * QQ_INPUT_POS[0]), int(SCREEN_SIZE.height * QQ_INPUT_POS[1]))
        OTHER_WINDOW_POS = (int(SCREEN_SIZE.width * OTHER_WINDOW_POS[0]), int(SCREEN_SIZE.height * OTHER_WINDOW_POS[1]))
        logger.debug(
            f"QQ_WINDOW_POS: {QQ_WINDOW_POS}, QQ_INPUT_POS: {QQ_INPUT_POS}, OTHER_WINDOW_POS: {OTHER_WINDOW_POS}"
        )
    TEMP_DIR = config.get("TEMP_DIR", TEMP_DIR)
    ASTRBOT_DATA_DIR = config.get("ASTRBOT_DATA_DIR", ASTRBOT_DATA_DIR)
    NOTIFICATION_REPEAT_COUNT = config.get("NOTIFICATION_REPEAT_COUNT", NOTIFICATION_REPEAT_COUNT)
    chat_id2chat_name, chat_name2chat_type, chat_name2chat_id, chat_id2chat_type = create_mapping(chat_info)


chat_id2chat_name, chat_name2chat_type, chat_name2chat_id, chat_id2chat_type = create_mapping(chat_info)
event_queue = asyncio.Queue()
send_message_id = random.randint(0, 99999999)
receive_message_id = random.randint(100000000, 199999999)
current_chat = None


def enable_log(func):
    def wrapper(*args, **kwargs):
        logger.debug(f"执行函数: {func.__name__}")
        return func(*args, **kwargs)

    return wrapper


@enable_log
def get_image_extension(decoded_bytes: bytes) -> str:
    """
    通过 imghdr 模块判断二进制数据是否为图片，并返回对应的文件扩展名。
    对于识别到的 'jpeg' 格式，将扩展名统一返回为 .jpg。
    如果不是图片，则返回空字符串。
    """
    image_type = imghdr.what(None, h=decoded_bytes)
    if image_type:
        return ".jpg" if image_type == "jpeg" else f".{image_type}"
    return ""


@enable_log
def save_base64_data(b64_string: str, output_dir="./", filename="file", extension=None) -> str:
    base64_prefix = "base64://"  # Base64 数据前缀
    file_data = None
    mime_type = None

    if b64_string.startswith(base64_prefix):
        # Base64 数据，形如 "base64://......"
        b64_string = b64_string[len(base64_prefix) :]
    elif b64_string.startswith("data:"):
        # Data URI 格式，形如 "data:image/png;base64,......"
        try:
            header, b64_string = b64_string.split(",", 1)
        except IndexError:
            raise ValueError("无效的 Data URI 格式")
        if ";base64" not in header:
            raise ValueError("仅支持 base64 编码的 Data URI")
        mime_type = header[5:].split(";")[0]  # 提取 MIME 类型

    file_data = pybase64.b64decode(b64_string)  # 解码 Base64 数据

    # 初始化 magic 对象（MIME 类型模式），通过 MIME 类型获取扩展名
    extension = (
        extension
        or mimetypes.guess_extension(mime_type or magic.Magic(mime=True).from_buffer(file_data))
        or get_image_extension(file_data)
    )
    # 如果无法通过 MIME 类型判断，使用描述模式
    if not extension:
        desc_magic = magic.Magic()
        file_desc = desc_magic.from_buffer(file_data).lower()
        # 常见文件类型关键词映射
        if "png" in file_desc:
            extension = ".png"
        elif "jpeg" in file_desc or "jpg" in file_desc:
            extension = ".jpg"
        elif "pdf" in file_desc:
            extension = ".pdf"
        elif "zip" in file_desc:
            extension = ".zip"
        elif "microsoft word" in file_desc:
            extension = ".docx"
        elif "excel" in file_desc:
            extension = ".xlsx"
        elif "gif" in file_desc:
            extension = ".gif"
        else:  # 默认使用 bin
            extension = ".bin"
    else:
        extension = extension  # 保持原样（包含点）

    # 清理扩展名（移除开头的点）
    extension = extension.lstrip(".").strip()

    # 生成文件名
    filename = f"{filename}.{extension}" if extension != "" else filename
    save_path = os.path.join(output_dir, filename)

    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 写入文件
    with open(save_path, "wb") as f:
        f.write(file_data)

    return save_path


@enable_log
def init_auto():
    # 初始化自动化环境
    os.makedirs(TEMP_DIR, exist_ok=True)
    pyperclip.copy("")
    # 设置 gsettings set org.gnome.desktop.interface enable-animations false
    subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "enable-animations", "false"], check=True)
    atexit.register(close_auto)


@enable_log
def close_auto():
    # 关闭自动化环境
    subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "enable-animations", "true"], check=True)


@enable_log
def copy_file_to_clipboard(file_path, file_name=None):
    os.makedirs(TEMP_DIR, exist_ok=True)
    if file_path.startswith("http"):
        # 网络路径
        temp_file = tui.download_file(file_path, os.path.join(TEMP_DIR, file_name) if file_name else TEMP_DIR)
        file_uri = f"file://{os.path.abspath(temp_file)}"
    elif file_path.startswith("file://"):
        # 本地路径
        # file_uri = file_path
        # 复制文件到临时目录
        temp_file = os.path.join(TEMP_DIR, file_name if file_name else os.path.basename(file_path))
        shutil.copy(file_path[7:], temp_file)
        file_uri = f"file://{os.path.abspath(temp_file)}"
    elif file_path.startswith("base64://") or file_path.startswith("data:"):
        # 将 base64 编码转换为文件
        # if file_path.startswith("base64://"):
        #     # 移除 "base64://" 前缀
        #     base64code = file_path.replace("base64://", "")
        # elif file_path.startswith("data:"):
        #     # data URI 格式，形如 "data:image/png;base64,......"
        #     # 分割取出逗号后面的部分
        #     try:
        #         base64code = file_path.split(",", 1)[1]
        #         file_ext = file_path.split(":", 1)[1].split(";", 1)[0].split("/", 1)[1]
        #         temp_file = f"{temp_file}.{file_ext}"
        #     except IndexError:
        #         raise ValueError("无效的 data URI 格式")
        # with open(temp_file, "wb") as f:
        #     f.write(base64.b64decode(base64code))
        temp_file = save_base64_data(file_path, TEMP_DIR, f"temp_{int(time.time())}")
        file_uri = f"file://{os.path.abspath(temp_file)}"
    else:
        # 验证文件存在性
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        temp_file = os.path.join(TEMP_DIR, file_name if file_name else os.path.basename(file_path))
        shutil.copy(file_path, temp_file)
        file_uri = f"file://{os.path.abspath(temp_file)}"

    # 使用 xclip 写入剪贴板
    subprocess.run(
        ["xclip", "-selection", "clipboard", "-t", "text/uri-list"], input=file_uri.encode("utf-8"), check=True
    )
    return temp_file


@enable_log
def safe_file_name(file_name):
    # return (
    #     file_name.replace(" ", "_")
    #     .replace("/", "_")
    #     .replace("\\", "_")
    #     .replace(":", "_")
    #     .replace("*", "_")
    #     .replace("?", "_")
    #     .replace('"', "_")
    #     .replace("<", "_")
    #     .replace(">", "_")
    #     .replace("|", "_")
    # )
    return re.sub(r'[\\/:*?"<>|]', "_", file_name)


@enable_log
def safe_copy_file(file_path, file_name=None) -> Optional[str]:
    try:
        if file_name:
            file_name = safe_file_name(file_name)
        temp_file = copy_file_to_clipboard(file_path, file_name)
        logger.debug(f"成功复制到剪贴板: {temp_file}")
        return temp_file
    except FileNotFoundError as e:
        logger.error(f"错误: {str(e)}")
    except subprocess.CalledProcessError:
        logger.error("xclip 执行失败，请确保已安装")
    except Exception as e:
        logger.error(f"未知错误: {str(e)}")
    return None


@enable_log
def qq_window_enter():
    """QQ 窗口按下回车键。"""
    pyautogui.press("enter")
    time.sleep(WAIT_TIME)


@enable_log
def qq_open(chat_name):
    """打开指定聊天窗口。"""
    global current_chat
    logger.debug(f"打开指定聊天窗口: {chat_name}")
    pyautogui.click(*QQ_WINDOW_POS, button="left")
    time.sleep(SMALL_WAIT_TIME)

    if current_chat == chat_name:
        return

    # 打开指定聊天窗口
    pyautogui.hotkey("ctrl", "f")
    time.sleep(SMALL_WAIT_TIME)
    pyautogui.typewrite(chat_name)
    time.sleep(WAIT_TIME)
    time.sleep(SMALL_WAIT_TIME)
    time.sleep(SMALL_WAIT_TIME)
    pyautogui.press("enter")
    time.sleep(SMALL_WAIT_TIME)
    current_chat = chat_name


@enable_log
def qq_close():
    """关闭 QQ 窗口。"""
    time.sleep(SMALL_WAIT_TIME)
    pyautogui.click(*OTHER_WINDOW_POS, button="left")


@enable_log
def qq_input_init():
    """进入输入模式。"""
    pyautogui.click(*QQ_INPUT_POS, button="left")
    # time.sleep(SMALL_WAIT_TIME)


@enable_log
def qq_input_send():
    """发送消息。"""
    pyautogui.hotkey("ctrl", "enter")
    time.sleep(SMALL_WAIT_TIME)


@enable_log
def qq_input_text(text):
    """输入文本。"""
    # pyautogui.typewrite(text)
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")
    # time.sleep(SMALL_WAIT_TIME)


@enable_log
def qq_input_at(qq_name):
    """输入 @ 某人。"""
    if qq_name == "all" or qq_name == "全体成员":
        pyautogui.typewrite("@")
    else:
        pyautogui.typewrite(f"@{qq_name}")
    time.sleep(SMALL_WAIT_TIME)
    pyautogui.hotkey("enter")


@enable_log
def qq_input_image(file_path):
    """输入图片。"""
    temp_file = safe_copy_file(file_path)
    if not temp_file:
        return
    pyautogui.hotkey("ctrl", "v")
    time.sleep(SMALL_WAIT_TIME)


@enable_log
def qq_send_file(file_path, file_name=None):
    """输入文件。"""
    if file_path.startswith("/AstrBot/data"):
        file_path = file_path.replace("/AstrBot/data", ".")
        file_path = os.path.join(ASTRBOT_DATA_DIR, file_path)
    temp_file = safe_copy_file(file_path, file_name)
    if not temp_file:
        return
    pyautogui.hotkey("ctrl", "v")
    pyautogui.keyDown("enter")
    time.sleep(SMALL_WAIT_TIME)
    pyautogui.keyUp("enter")
    # 1h 后删除临时文件
    # os.remove(temp_file)


@enable_log
def qq_send_message(message_type: Literal["group", "private"], chat_id: str, message: list):
    """将 msg 发送给 to 指定的对象。"""
    global send_message_id
    chat_id = str(chat_id)
    logger.debug(f"发送消息: {chat_id}, {message}")
    if not isinstance(message, list):
        logger.error(f"消息格式错误, chat_name: {chat_id}, message: {message}")
        return None
    try:
        qq_open(chat_id)
        qq_input_init()
        text_gather = ""
        has_input_text = False
        for item in message:
            if item["type"] == "text":
                text_gather += item["data"]["text"].strip()
                has_input_text = True
                continue
            elif item["type"] == "json":
                text_gather += item["data"]["data"].strip()
                has_input_text = True
                continue
            elif text_gather != "":
                qq_input_text(text_gather)
                text_gather = ""
            if item["type"] == "at":
                if message_type == "group":
                    qq_input_at(chat_id2chat_name.get(str(item["data"]["qq"]), item["data"]["qq"]))
                    has_input_text = True
            elif item["type"] == "image":
                qq_input_image(item["data"]["file"])
                has_input_text = True
            elif item["type"] == "file":
                qq_send_file(item["data"]["file"], item["data"]["name"])
                qq_input_init()
            else:
                logger.warning(f"不支持的消息类型: {item}")
        if text_gather != "":
            qq_input_text(text_gather)
        if has_input_text:
            qq_input_send()
        qq_close()
    except Exception as e:
        logger.error(f"发送消息失败, chat_name: {chat_id}, message: {message}, error: {e}")
        qq_close()
        return None
    send_message_id += 1
    return send_message_id


# # 同步处理消息的函数
# def process_task_blocking(task: dict):
#     # # /help 命令
#     # if message["content"] == "/help":
#     #     qq_send_message("这是一个示例机器人。\n/help 显示此帮助信息。\n/file 发送文件。\n", message["from"])
#     # # /file 命令
#     # elif message["content"] == "/file":
#     #     send_file("test.txt", message["from"])
#     # # 其他消息
#     # else:
#     #     # send_message("你发送了一条消息: " + message["content"], message["from"])
#     #     print("你发送了一条消息: " + message["content"], message["from"])
#     task_action = task.get("action", "")
#     if task_action == "send_message":
#         send_message_id = qq_send_message(task["chat_name"], task["message"])
#         if send_message_id is None:
#             logger.error(f"发送消息失败: {task}")
#         else:
#             logger.info(f"发送消息成功: {task}")
#     elif task_action == "send_file":
#         send_file(task["file"], task["chat_name"])
#         logger.info(f"发送文件成功: {task}")


# # 异步 wrapper，通过 asyncio.to_thread 将同步处理放入线程中执行
# async def process_task(task: dict):
#     await asyncio.to_thread(process_task_blocking, task)


# # 消息消费者，从队列中取出消息并依次处理，确保 process_message 串行执行
# async def task_consumer():
#     while True:
#         task = await task_queue.get()
#         await process_task(task)
#         task_queue.task_done()


async def get_event():
    global event_queue
    if event_queue.empty():
        return None
    return await event_queue.get()


async def message_monitor():
    global event_queue, chat_name2chat_type, chat_name2chat_id, receive_message_id, self_id, self_name, NOTIFICATION_REPEAT_COUNT
    """
    实时获取输出。
    由于每条消息会重复输出2次，这里简单通过比较和去重的方式进行处理。
    """
    command = r"""dbus-monitor "path='/org/freedesktop/Notifications',interface='org.freedesktop.Notifications',member='Notify'" \
| stdbuf -oL awk '
/string "QQ"/ {
    capture = 1
    next
}
/string ""/ {
    if (capture == 1) {
        capture = 2
    } else {
        capture = 0
    }
    next
}
capture == 2 && /array \[/ {
    print buffer
    buffer = ""
    capture = 0
    next
}
capture == 2 {
    buffer = buffer "\n" $0
}' 
"""
    # 启动子进程
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        shell=True,
    )

    hash_count = {}
    qq_close()
    # 持续读取输出
    while True:
        buffer = []
        while len(buffer) < 2:
            line = await proc.stdout.readline()
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            line = line.split('"')[1]  # 匹配双引号内的内容
            buffer.append(line)

        logger.debug(f'收到消息: "{buffer[0]}" "{buffer[1]}"')

        chat_name = buffer[0].strip()
        notify_content: str = buffer[1]

        # 检查是否为有效消息
        if NOTIFICATION_REPEAT_COUNT > 1:
            hash_count[chat_name + notify_content] = hash_count.get(chat_name + notify_content, 0) + 1
            if hash_count[chat_name + notify_content] >= NOTIFICATION_REPEAT_COUNT:
                hash_count.pop(chat_name + notify_content)
                continue

        # 过滤掉无效消息："你有xx条新消息"
        if notify_content.startswith("你有") and notify_content.endswith("条新通知"):
            logger.debug(f"过滤掉无效消息: {notify_content}")
            continue

        # 过滤掉纯文本以外的消息
        # if notify_content.startswith("[") and notify_content.endswith("]"):
        #     logger.debug(f"过滤掉非文本消息: {notify_content}")
        #     continue

        message = []
        chat_type = chat_name2chat_type.get(str(chat_name), "group")
        logger.debug(f"chat_name: {chat_name}, notify_content: {notify_content} chat_type: {chat_type}")

        if chat_type == "group":
            at_flag = False
            if notify_content.startswith("[有人@我] "):
                notify_content = notify_content.replace("[有人@我] ", "")
                notify_content = notify_content.replace(f"@{self_name} ", "")
                at_flag = True
            raw_message = notify_content.split("：", 1)[1]
            sender_nickname = notify_content.split("：")[0]
            sender_user_id = chat_name2chat_id.get(sender_nickname, 0)
            if at_flag:
                message.append({"type": "at", "data": {"qq": int(self_id)}})
            event = {
                "time": int(time.time()),
                "post_type": "message",
                "message_type": "group",
                "sub_type": "normal",
                "message_id": receive_message_id,
                "group_id": chat_name2chat_id.get(chat_name, 0),
                "user_id": sender_user_id,
                "message": message + [{"type": "text", "data": {"text": raw_message}}],
                "raw_message": raw_message,
                "sender": {
                    "user_id": sender_user_id,
                    "nickname": sender_nickname,
                    "role": "member",
                },
            }
        else:
            sender_nickname = chat_name
            raw_message = notify_content
            event = {
                "time": int(time.time()),
                "post_type": "message",
                "message_type": "private",
                "sub_type": "friend",
                "message_id": receive_message_id,
                "user_id": chat_name2chat_id.get(sender_nickname, 0),
                "message": [{"type": "text", "data": {"text": raw_message}}],
                "raw_message": raw_message,
                "sender": {
                    "user_id": chat_name2chat_id.get(sender_nickname, 0),
                    "nickname": sender_nickname,
                },
            }

        receive_message_id += 1
        logger.info(f"收到消息: {event}")
        await event_queue.put(event)


# async def main():
#     # 主函数，用于运行监控命令
#     asyncio.create_task(task_consumer(task_queue))
#     asyncio.create_task(run_app())
#     await message_monitor(task_queue)


# async def main():
#     # 主函数，用于运行监控命令
#     await message_monitor()


# if __name__ == "__main__":
#     asyncio.run(main())
