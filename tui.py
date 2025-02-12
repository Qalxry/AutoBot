import os
import sys
import cgi
import time
import yaml
import json
import shutil
import atexit
import zipfile
import datetime
import tempfile
import requests
import itertools
import threading
import questionary

from questionary import Choice
from collections.abc import MutableMapping
from dateutil.parser import parse as parse_date
from urllib.parse import urlparse, unquote, urlunparse
from requests.exceptions import RequestException, HTTPError
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Literal, Union, Iterable, Callable, Any, Dict, Tuple
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
    TaskID,
)

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self):
        return self.value


class IntEnum(int, Enum):
    def __str__(self):
        return self.value


def recursive_update(original: dict, update: dict) -> dict:
    for key, value in update.items():
        if key in original and isinstance(original[key], dict) and isinstance(value, dict):
            original[key] = recursive_update(original[key], value)
        else:
            original[key] = value
    return original


class RichProgress:
    """
    仿 tqdm 接口的 Rich 进度条，支持底部固定显示 + 常规日志分离

    示例：
    >>> with RichProgress(total=100, desc="Processing") as pbar:
    ...     for i in range(100):
    ...         pbar.log(f"Processing item {i}")
    ...         print(f"Processing item {i}", end="\r")
    ...         time.sleep(0.1)
    ...         pbar.update(1)
    >>> for item in RichProgress(range(100), desc="Processing"):
    ...     time.sleep(0.1)
    ...     pass
    """

    def __init__(
        self,
        iterable: Optional[Iterable] = None,
        total: Optional[int] = None,
        desc: str = "Progress",
        console: Optional[Console] = None,
        bar_width: Optional[int] = 40,
        disable: bool = False,
        transient: bool = False,
        **kwargs,
    ):
        # 参数处理
        self.iterable = iterable
        self.total = total if total is not None else (len(iterable) if iterable else None)
        self.desc = desc
        self.console = console or Console()
        self.completed = 0
        # 进度条配置
        self.progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            SpinnerColumn(finished_text="[green]✓"),
            BarColumn(bar_width=bar_width),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[progress.completed]({task.completed}/{task.total})"),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
            console=self.console,
            transient=transient,
            disable=disable,
            **kwargs,
        )
        self._task_id: Optional[TaskID] = None
        self._is_running = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self):
        """启动进度条"""
        if not self._is_running:
            self.progress.start()
            self._task_id = self.progress.add_task(self.desc, total=self.total)
            self._is_running = True
            self.completed = 0

    def is_finished(self) -> bool:
        """判断进度条是否完成"""
        return self.completed == self.total

    def update(self, n: int = 1, description: Optional[str] = None):
        """更新进度"""
        if self._task_id is not None:
            if description:
                self.progress.update(self._task_id, description=description)
            self.progress.advance(self._task_id, advance=n)
            self.completed += n

    def log(self, message: str, wrap: bool = True):
        """在进度条上方输出日志（自动换行）"""
        self.console.print(message, soft_wrap=wrap, highlight=False)

    def close(self):
        """关闭进度条"""
        if self._is_running:
            self.progress.stop()
            self._is_running = False

    def set_description(self, desc: str):
        """动态更新描述文本"""
        if self._task_id is not None:
            self.progress.update(self._task_id, description=desc)

    def __iter__(self):
        """支持迭代器模式"""
        self.start()
        if self.iterable is None:
            raise ValueError("iterable must be provided for iteration")
        for item in self.iterable:
            yield item
            self.update(1)
        self.close()


class YamlDict(MutableMapping):
    def __init__(
        self,
        file_path,
        mode: Literal["r", "w", "rw"] = "rw",
        *args,
        save_after_change_count: int = None,
        **kwargs,
    ):
        self.file_path = file_path
        self.save_after_change_count = save_after_change_count or 999999999  # 修改多少次后保存
        self._change_count = 0  # 修改计数器
        self.mode = mode
        self.load()
        self.update(*args, **kwargs)
        atexit.register(self.save)  # 在程序退出时保存数据

    def load(self):
        """从 YAML 文件加载数据"""
        if not os.path.exists(self.file_path) and self.mode == "w":
            os.makedirs(os.path.dirname(self.file_path) or "./", exist_ok=True)
            with open(self.file_path, "w") as f:
                yaml.dump({}, f)
        try:
            if self.mode != "w":
                with open(self.file_path, "r") as f:
                    self._data = yaml.safe_load(f) or {}  # 如果文件为空，返回空字典
            else:
                self._data = {}
        except (FileNotFoundError, yaml.YAMLError):
            if self.mode == "r":
                raise FileNotFoundError(f"File not found: {self.file_path}")
            self._data = {}

    def save(self):
        """将数据保存到 YAML 文件"""
        if self.mode == "r":
            return
        with open(self.file_path, "w") as f:
            yaml.dump(self._data, f, default_flow_style=False)

    def _increment_change_count(self):
        """增加修改计数器，并在达到阈值时保存"""
        self._change_count += 1
        if self._change_count >= self.save_after_change_count:
            self.save()
            self._change_count = 0  # 重置计数器

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value
        self._increment_change_count()

    def __delitem__(self, key):
        del self._data[key]
        self._increment_change_count()

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __repr__(self):
        return repr(self._data)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.save()  # 退出上下文时保存数据


class JsonDict(MutableMapping):
    def __init__(
        self,
        file_path,
        mode: Literal["r", "w", "rw"] = "r",
        *args,
        save_after_change_count: int = None,
        **kwargs,
    ):
        self.file_path = file_path
        self.save_after_change_count = save_after_change_count or 999999999  # 修改多少次后保存
        self._change_count = 0  # 修改计数器
        self.mode = mode
        self.load()
        self.update(*args, **kwargs)
        atexit.register(self.save)  # 在程序退出时保存数据

    def load(self):
        """从 JSON 文件加载数据"""
        if not os.path.exists(self.file_path) and self.mode == "w":
            os.makedirs(os.path.dirname(self.file_path) or "./", exist_ok=True)
            with open(self.file_path, "w") as f:
                json.dump({}, f)
        try:
            if self.mode != "w":
                with open(self.file_path, "r") as f:
                    self._data = json.load(f)
            else:
                self._data = {}
        except (FileNotFoundError, json.JSONDecodeError):
            if self.mode == "r":
                raise FileNotFoundError(f"File not found: {self.file_path}")
            self._data = {}

    def save(self):
        """将数据保存到 JSON 文件"""
        if self.mode == "r":
            return
        with open(self.file_path, "w") as f:
            json.dump(self._data, f, indent=4)

    def _increment_change_count(self):
        """增加修改计数器，并在达到阈值时保存"""
        self._change_count += 1
        if self._change_count >= self.save_after_change_count:
            self.save()
            self._change_count = 0  # 重置计数器

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value
        self._increment_change_count()

    def __delitem__(self, key):
        del self._data[key]
        self._increment_change_count()

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __repr__(self):
        return repr(self._data)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.save()  # 退出上下文时保存数据


class JsonProxy:
    """
    A proxy class that interfaces with a JSON file and allows attribute-based
    read and write access. It supports optional autosave functionality and can
    operate in different modes to handle reading, writing, or both.
    Attributes:
        _JsonProxy__json_file (str): The path to the JSON file to be managed.
        _JsonProxy__mode (Literal["r", "w", "rw"]): The mode in which the file is accessed.
        _JsonProxy__save_after_change_count (Optional[int]): Number of changes after which
            the data is persisted automatically. If None, data is saved on every change.
        _JsonProxy__change_count (int): Internal counter tracking the number of modifications
            since the last save.
    """

    def __init__(
        self,
        json_file: str,
        mode: Literal["r", "w", "rw"] = "r",
        save_after_change_count: Optional[int] = None,
    ):
        """
        Initialize the JsonProxy instance, load data from the specified JSON file,
        and register a save operation to occur automatically when the program
        exits.

        Args:
            json_file (str): Path to the JSON file.

            mode (Literal["r", "w", "rw"]): Access mode for the JSON file:
                - "r" for read-only,
                - "w" for write-only,
                - "rw" for read/write.

            save_after_change_count (Optional[int]): Number of attribute changes after which
                data is saved automatically. If None, data is saved every time an attribute
                is changed.
        """
        self._JsonProxy__json_file = json_file
        self._JsonProxy__mode = mode
        self._JsonProxy__save_after_change_count = save_after_change_count
        self._JsonProxy__change_count = 0
        self.load()
        atexit.register(self.save)  # 在程序退出时保存数据

    def load(self):
        """
        Load data from the JSON file into the current instance's attributes.
        If the file is not found or is invalid JSON, behavior depends on the mode:
        - If mode is "w", create an empty file if it doesn't exist.
        - If mode is "r" and the file doesn't exist or is corrupt, raise FileNotFoundError.
        """

        if self._JsonProxy__mode == "w":
            if not os.path.exists(self._JsonProxy__json_file):
                os.makedirs(os.path.dirname(self._JsonProxy__json_file) or "./", exist_ok=True)
                with open(self._JsonProxy__json_file, "w") as f:
                    json.dump({}, f)
        else:
            try:
                with open(self._JsonProxy__json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, value in data.items():
                        setattr(self, key, value)
            except (FileNotFoundError, json.JSONDecodeError):
                if self._JsonProxy__mode == "r":
                    raise FileNotFoundError(f"File not found: {self._JsonProxy__json_file}")

    def save(self):
        """
        Save the current instance's non-private attributes to the JSON file,
        respecting the mode setting. If the mode is "r", this method does nothing.
        """
        if self._JsonProxy__mode == "r":
            return
        data = {key: value for key, value in self.__dict__.items() if not key.startswith("_JsonProxy_")}
        os.makedirs(os.path.dirname(self._JsonProxy__json_file) or "./", exist_ok=True)
        with open(self._JsonProxy__json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def __setattr__(self, name: str, value: Any):
        """
        Override default behavior to automatically trigger a save operation
        (or increment a change counter) whenever a non-private attribute changes.
        """
        super().__setattr__(name, value)
        if name.startswith("_JsonProxy_") or "_JsonProxy__save_after_change_count" not in self.__dict__:
            return
        if self._JsonProxy__save_after_change_count is None:
            self.save()
        elif self._JsonProxy__change_count >= self._JsonProxy__save_after_change_count:
            self.save()
            self._JsonProxy__change_count = 0
        else:
            self._JsonProxy__change_count += 1

    def __delattr__(self, name: str):
        """
        Override default behavior to automatically trigger a save operation
        (or increment a change counter) whenever a non-private attribute is deleted.
        """
        super().__delattr__(name)
        if name.startswith("_JsonProxy_") or "_JsonProxy__save_after_change_count" not in self.__dict__:
            return
        if self._JsonProxy__save_after_change_count is None:
            self.save()
        elif self._JsonProxy__change_count >= self._JsonProxy__save_after_change_count:
            self.save()
            self._JsonProxy__change_count = 0
        else:
            self._JsonProxy__change_count += 1

    def __iter__(self):
        """
        Return an iterator over the non-private attributes of the instance.
        """
        return iter({key: value for key, value in self.__dict__.items() if not key.startswith("_JsonProxy_")})

    def __len__(self):
        """
        Return the number of non-private attributes of the instance.
        """
        return len([key for key in self.__dict__ if not key.startswith("_JsonProxy_")])

    def __enter__(self):
        """
        Enter the runtime context related to this object, returning self.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the runtime context and save data to the JSON file.
        """
        self.save()  # 退出上下文时保存数据

    def __str__(self):
        """
        Return a string representation of all non-private attributes of the instance.
        """
        return str({key: value for key, value in self.__dict__.items() if not key.startswith("_JsonProxy_")})


def cpwhite(text, verbose=True, end="\n"):
    if verbose:
        print(text + end, end="")


def cpgreen(text, verbose=True, end="\n"):
    if verbose:
        print(f"\033[32m{text}\033[0m" + end, end="")  # 这样写保证并发时不会出现换行问题


def cpred(text, verbose=True, end="\n"):
    if verbose:
        print(f"\033[31m{text}\033[0m" + end, end="")


def cpblue(text, verbose=True, end="\n"):
    if verbose == True:
        print(f"\033[34m{text}\033[0m" + end, end="")


def cpyellow(text, verbose=True, end="\n"):
    if verbose == True:
        print(f"\033[33m{text}\033[0m" + end, end="")


def cporange(text, verbose=True, end="\n"):
    if verbose == True:
        print(f"\033[38;5;208m{text}\033[0m" + end, end="")


def cppurple(text, verbose=True, end="\n"):
    if verbose == True:
        print(f"\033[35m{text}\033[0m" + end, end="")


def cpcyan(text, verbose=True, end="\n"):
    if verbose == True:
        print(f"\033[36m{text}\033[0m" + end, end="")


def cpgrey(text, verbose=True, end="\n"):
    if verbose == True:
        print(f"\033[90m{text}\033[0m" + end, end="")


def cpbold(text, verbose=True, end="\n"):
    if verbose == True:
        print(f"\033[1m{text}\033[0m" + end, end="")


def cpunderline(text, verbose=True, end="\n"):
    if verbose == True:
        print(f"\033[4m{text}\033[0m" + end, end="")


def cpitalic(text, verbose=True, end="\n"):
    if verbose == True:
        print(f"\033[3m{text}\033[0m" + end, end="")


def cpstrikethrough(text, verbose=True, end="\n"):
    if verbose == True:
        print(f"\033[9m{text}\033[0m" + end, end="")


def cpclear():
    os.system("cls" if os.name == "nt" else "clear")


def clear_input_buffer():
    """清空标准输入缓冲区"""
    try:
        import msvcrt  # Windows 平台

        while msvcrt.kbhit():
            msvcrt.getch()
    except ImportError:
        import termios  # Linux/Unix 平台

        termios.tcflush(sys.stdin, termios.TCIOFLUSH)


def clear_input_buffer():
    """清空标准输入缓冲区"""
    try:
        import msvcrt  # Windows 平台

        while msvcrt.kbhit():
            msvcrt.getch()
    except ImportError:
        import termios  # Linux/Unix 平台

        termios.tcflush(sys.stdin, termios.TCIOFLUSH)


def select(
    message: str,
    selections: list[str],
    default: int | str = 0,
    return_index: bool = False,
    skip: bool = False,
) -> str | int:
    """选择界面"""
    assert len(selections) > 0, "选项列表不能为空"
    assert 0 <= default < len(selections), "默认选项超出范围"
    default_choice = selections[default] if type(default) == int else default
    if skip:
        res = default_choice
    else:
        time.sleep(0.001)
        clear_input_buffer()
        print("\r", end="")
        res = questionary.select(
            message,
            choices=selections,
            default=default_choice,
            instruction="(使用 ↑/↓ 选择, Enter 确认) ",
        ).ask()
    if res is None:
        raise KeyboardInterrupt
    if return_index:
        return selections.index(res)
    return res


def confirm(
    message: str,
    default: bool = True,
    skip: bool = False,
) -> bool:
    """确认界面"""
    if skip:
        return default
    else:
        time.sleep(0.001)
        clear_input_buffer()
        print("\r", end="")
        res = questionary.confirm(message, default=default, auto_enter=True).ask()
    if res is None:
        raise KeyboardInterrupt
    return res


def multi_select(
    message: str,
    selections: list[str],
    default: list[int | str] = [],
    return_index: bool = False,
    skip: bool = False,
) -> list[str | int]:
    """多选界面"""
    assert len(selections) > 0, "选项列表不能为空"
    assert all(0 <= i < len(selections) for i in default), "默认选项超出范围"

    default_choice_index = []
    if len(default) != 0:
        default_choice_index = [selections.index(i) for i in default] if type(default[0]) == str else default
    if skip:
        res = default_choice_index
    else:
        time.sleep(0.001)
        clear_input_buffer()
        print("\r", end="")
        res = questionary.checkbox(
            message,
            choices=[
                Choice(selection, value=idx, checked=idx in default_choice_index)
                for idx, selection in enumerate(selections)
            ],
            instruction="(使用 ↑/↓ 选择, Space 选中, Enter 确认) ",
        ).ask()
    if res is None:
        raise KeyboardInterrupt
    if return_index:
        return res
    return [selections[i] for i in res]


def password(
    message: str = "请输入密码",
    correct_password: str = None,
    validater=None,
    skip: bool = False,
) -> str:
    """密码输入界面"""
    if skip:
        res = correct_password
    else:
        time.sleep(0.001)
        clear_input_buffer()
        print("\r", end="")
        res = questionary.password(
            message,
            validate=validater or (lambda text: (text == correct_password or "密码错误" if correct_password else True)),
            instruction="(输入密码, Enter 确认) ",
        ).ask()

    if res is None:
        raise KeyboardInterrupt
    return res


def input(
    message: str,
    default: str = "",
    multiline: bool = False,
    validater=None,
    skip: bool = False,
) -> str:
    """输入界面"""
    if skip:
        res = default
    else:
        time.sleep(0.001)
        clear_input_buffer()
        print("\r", end="")
        res = questionary.text(
            message,
            default=default,
            instruction=(
                "(输入文本, Enter 确认) " if not multiline else "(输入文本, Alt+Enter 结束, 或者 Esc 然后 Enter)\n>"
            ),
            validate=validater,
            multiline=multiline,
        ).ask()
    if res is None:
        raise KeyboardInterrupt
    return res


def prompt(questions: list[dict]) -> dict:
    """批量问题
    输入示例：
    questions = [
        {
            "name": "select",
            "type": "select",
            "message": "请选择一个选项",
            "selections": ["选项1", "选项2", "选项3"],
            "default": 1,
            "return_index": True,
            "skip": False,
        },
        {
            "name": "confirm",
            "type": "confirm",
            "message": "是否继续",
            "default": False,
            "skip": False,
        },
        {
            "name": "multi_select",
            "type": "multi_select",
            "message": "请选择多个选项",
            "selections": ["选项1", "选项2", "选项3"],
            "default": [0, 2],
            "return_index": True,
            "skip": False,
        },
        {
            "name": "password",
            "type": "password",
            "message": "请输入密码",
            "correct_password": "123",
            "validater": None,
            "skip": False,
        },
        {
            "name": "input",
            "type": "input",
            "message": "请输入文本",
            "default": "默认文本",
            "validater": None,
            "skip": False,
        },
    ]
    answers = prompt(questions)
    answers = {
        "select": 1,
        "confirm": False,
        "multi_select": [0, 2],
        "password": "123",
        "input": "默认文本",
    }
    """
    answers = {}
    for i, question in enumerate(questions):
        # 如果没有 name 字段，自动添加为问题的索引
        if "name" not in question:
            question["name"] = str(i)

        if question["type"] == "select":
            answers[question["name"]] = select(
                question["message"],
                question["selections"],
                question.get("default", 0),
                question.get("return_index", False),
                question.get("skip", False),
            )
        elif question["type"] == "confirm":
            answers[question["name"]] = confirm(
                question["message"],
                question.get("default", True),
                question.get("skip", False),
            )
        elif question["type"] == "multi_select":
            answers[question["name"]] = multi_select(
                question["message"],
                question["selections"],
                question.get("default", []),
                question.get("return_index", False),
                question.get("skip", False),
            )
        elif question["type"] == "password":
            answers[question["name"]] = password(
                question["message"],
                question.get("correct_password", None),
                question.get("validater", None),
                question.get("skip", False),
            )
        elif question["type"] == "input":
            answers[question["name"]] = input(
                question["message"],
                question.get("default", ""),
                question.get("validater", None),
                question.get("skip", False),
            )

    return answers


class LoadingAnimation:
    def __init__(
        self,
        message: str = "",
        style: Literal["dots", "spinner"] = "dots",
        speed: float = None,
        immediate: bool = True,
        transient: bool = False,
        end="\n",
        enable: bool = True,
    ):
        """初始化 LoadingAnimation 类"""
        self.loading_animation_status = False  # 控制动画是否运行
        self.loading_animation_thread = None  # 动画线程
        self.style = style
        self.message = message
        atexit.register(self.stop)  # 在程序退出时停止动画
        if speed is None:
            if style == "dots":
                speed = 0.3
            elif style == "spinner":
                speed = 0.1
        self.speed = speed
        self.end = end
        self.transient = transient
        self.enable = enable
        if immediate:
            self.start(message)

    def start(self, message=""):
        """开始动画"""
        self.stop()  # 停止之前的动画
        self.loading_animation_status = False  # 允许动画运行
        self.message = message

        def animation():
            """生成动画"""
            if self.style == "dots":
                frames = itertools.cycle([".", ".", ".", "\b\b\b   \b\b\b"])  # 闪烁的点
            elif self.style == "spinner":
                frames = itertools.cycle(["|\b", "/\b", "-\b", "\\\b"])  # 旋转的光标符号
            while not self.loading_animation_status:
                sys.stdout.write(next(frames))  # 显示下一个光标符号
                sys.stdout.flush()
                time.sleep(self.speed)  # 速度

        if self.enable:
            print(self.message, end=" ")
            # 隐藏光标
            sys.stdout.write("\033[?25l")
            """启动动画"""
            if self.loading_animation_thread is None or not self.loading_animation_thread.is_alive():
                self.loading_animation_status = False  # 允许动画运行
                self.loading_animation_thread = threading.Thread(target=animation, daemon=True)
                self.loading_animation_thread.start()

    def stop(self):
        """停止动画"""
        if self.loading_animation_thread and self.loading_animation_thread.is_alive():
            self.loading_animation_status = True  # 停止动画运行
            self.loading_animation_thread.join()  # 等待动画线程结束
            # 清除一行
            if self.transient:
                sys.stdout.write("\r" + " " * 50 + "\r")
            sys.stdout.write("\033[?25h")  # 显示光标
            sys.stdout.write(self.end)  # 换行
            sys.stdout.flush()

    def __del__(self):
        """对象销毁时停止动画"""
        self.stop()
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()  # 退出上下文时停止动画


def ensure_date(*args) -> Union[datetime.date, tuple[datetime.date]]:
    """确保日期格式"""
    ret = ()
    for arg in args:
        if isinstance(arg, datetime.date):
            ret += (arg,)
        elif isinstance(arg, datetime.datetime):
            ret += (arg.date(),)
        elif isinstance(arg, str):
            ret += (parse_date(arg).date(),)
        else:
            raise ValueError(f"Invalid date: {arg}")
    if len(ret) == 1:
        return ret[0]
    return ret


# def list_date(
#     since: datetime.date | str,
#     until: datetime.date | str,
#     step: Literal["day", "week", "month", "year"] = "day",
# ) -> List[datetime.date]:
#     """生成日期数组"""
#     if isinstance(since, datetime.datetime):
#         since = since.date()
#     if isinstance(until, datetime.datetime):
#         until = until.date()
#     if isinstance(since, str):
#         since = parse_date(since).date()
#     if isinstance(until, str):
#         until = parse_date(until).date()
#     if step == "day":
#         return [since + datetime.timedelta(days=i) for i in range((until - since).days + 1)]
#     elif step == "week":
#         return [since + datetime.timedelta(weeks=i) for i in range((until - since).days // 7 + 1)]
#     elif step == "month":
#         return [
#             datetime.date(
#                 since.year + (since.month - 1 + i) // 12,
#                 (since.month - 1 + i) % 12 + 1,
#                 1,
#             )
#             for i in range((until.year - since.year) * 12 + until.month - since.month + 1)
#         ]
#     elif step == "year":
#         return [datetime.date(since.year + i, 1, 1) for i in range(until.year - since.year + 1)]
#     else:
#         raise ValueError("Invalid step")


# def range_date(
#     since: datetime.date | str,
#     until: datetime.date | str,
#     step: Literal["day", "week", "month", "year"] = "day",
# ) -> Iterable[datetime.date]:
#     """生成日期范围"""
#     temp = list_date(since, until, step)
#     for i in range(len(temp) - 1):
#         yield temp[i]


def get_filename_from_response(response, url):
    """
    从 HTTP 响应头或 URL 中提取文件名（处理 RFC 5987 编码和特殊字符）
    """
    # 处理 Content-Disposition 头
    content_disposition = response.headers.get("Content-Disposition", "")
    if content_disposition:
        # 使用 cgi 解析头部（兼容复杂格式）
        _, params = cgi.parse_header(content_disposition)
        filename = params.get("filename*") or params.get("filename")
        if filename:
            # 处理 RFC 5987 编码（例如：filename*=UTF-8''%E6%96%87%E6%9C%AC.txt）
            if filename.startswith("UTF-8''"):
                filename = unquote(filename[7:])
            return filename

    # 清理 URL 中的查询参数和片段
    parsed_url = urlparse(url)
    clean_url = parsed_url._replace(query="", fragment="")
    clean_path = urlunparse(clean_url).split("?")[0]
    filename = unquote(os.path.basename(clean_path))

    # 如果 URL 路径为空，返回默认文件名
    return filename if filename else f"unknown_{int(time.time())}"


def get_filename_from_url(url):
    """从 URL 中提取文件名"""
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)
    return unquote(filename) if filename else ""


def safe_replace(
    source: str,
    destination: str,
    overwrite: bool = False,
):
    """安全替换文件或目录（兼容跨设备）"""
    if not os.path.exists(source):
        raise FileNotFoundError(f"Source '{source}' does not exist")
    if os.path.abspath(source) == os.path.abspath(destination):
        return
    if os.path.isfile(source):
        # 处理文件情况
        if os.path.isdir(destination):
            # 目标为目录，拼接文件名
            destination = os.path.join(destination, os.path.basename(source))
        if os.path.exists(destination):
            # 目标存在，报错
            if not overwrite:
                raise ValueError(f"Destination '{destination}' already exists")
            # 目标存在，删除
            os.remove(destination)
        # 现在destination是文件路径
        try:
            os.replace(source, destination)
        except OSError as e:
            if e.errno != 18:  # 非跨设备错误
                raise
            # 跨设备，复制后删除
            shutil.copy2(source, destination)
            os.remove(source)

    elif os.path.isdir(source):
        # 处理目录情况
        if os.path.isfile(destination):
            raise ValueError("Cannot replace a file with a directory")
        # 如果目标存在，报错
        if os.path.exists(destination):
            # 目标存在，删除
            if not overwrite:
                raise ValueError(f"Destination '{destination}' already exists")
            shutil.rmtree(destination)
        # 现在destination是目录路径
        try:
            os.replace(source, destination)
        except OSError as e:
            if e.errno != 18:  # 非跨设备错误
                raise
        # 跨设备，递归复制后删除
        shutil.copytree(source, destination)
        shutil.rmtree(source)
    else:
        raise ValueError(f"Source '{source}' is not a file or directory")


def is_url_exists(
    url,
    user_agent=None,
    max_retries=3,
    timeout=3,
    verbose=False,
):
    """
    检查 URL 是否存在（不下载文件内容）

    Args:
        url (str): 要检测的 URL
        user_agent (str): 自定义 User-Agent（可绕过某些服务器限制）
        timeout (int): 超时时间（秒）

    Returns:
        bool: True 表示资源存在且可访问，False 表示不存在或无法确认
    """
    headers = {
        # 强制绕过缓存（重要！）
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
        "User-Agent": user_agent or "Mozilla/5.0",
    }
    for attempt in range(max_retries):
        try:
            # 先尝试 HEAD 请求
            response = requests.head(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=timeout,  # 跟随重定向
            )

            # 如果 HEAD 返回 405（方法不支持），改用 GET 请求（不下载内容）
            if response.status_code == 405:
                cpblue("[备注] HEAD 请求失败，改用 GET 请求", verbose)
                response = requests.get(url, headers=headers, stream=True, timeout=timeout)  # 不立即下载内容
                response.close()  # 立即关闭连接

            # 关键状态码判断逻辑
            if response.status_code == 200:
                cpgreen(f"[成功] 文件 {url} 存在（状态码 {response.status_code}）", verbose)
                return True
            elif response.status_code in (401, 403):
                cporange(
                    f"[重试 {attempt+1}/{max_retries}] 权限不足（状态码 {response.status_code}），文件可能存在但无法访问",
                    verbose,
                )
            elif response.status_code == 404:
                cporange(
                    f"[失败] 文件 {url} 不存在（状态码 {response.status_code}）",
                    verbose,
                )
                return False
            else:
                cporange(
                    f"[重试 {attempt+1}/{max_retries}] 未知状态码 {response.status_code}，无法确认文件是否存在",
                    verbose,
                )
        except RequestException as e:
            cporange(f"[重试 {attempt+1}/{max_retries}] 请求失败: {str(e)}", verbose)

    cporange(f"[失败] URL ({url}) 检查失败", verbose)
    return False


def is_url_exists_batch(
    urls: list[str],
    num_workers: int = 8,
    user_agent=None,
    max_retries=3,
    timeout=3,
    verbose=False,
    progress_bar=False,
) -> list[bool]:
    """
    批量检查 URL 是否存在（多线程并发版本）

    Args:
        urls (list): 要检测的 URL 列表
        num_workers (int): 并发线程数
        user_agent (str): 自定义 User-Agent
        timeout (int): 超时时间（秒）
        verbose (bool): 是否打印详细日志
        progress_bar (bool): 是否显示进度条

    Returns:
        list: 每个 URL 的检测结果（按原始顺序）
    """
    results = [False] * len(urls)

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # 建立 future 到索引的映射关系
        future_to_idx = {
            executor.submit(
                is_url_exists,
                url,
                user_agent=user_agent,
                max_retries=max_retries,
                timeout=timeout,
                verbose=verbose,
            ): idx
            for idx, url in enumerate(urls)
        }
        with RichProgress(total=len(urls), desc="检查 URL", disable=not progress_bar) as pbar:
            # 按完成顺序处理结果
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    if verbose:
                        cpred(f"[错误] URL ({urls[idx]}) 检查异常: {str(e)}")
                    results[idx] = False
                finally:
                    pbar.update(1)
    return results


def download_file(
    url,
    dest_path,
    max_retries=3,
    exist_ok=True,
    temp_dir=None,
    chunk_size=8192,
    verbose=True,
) -> Optional[str]:
    """
    下载文件到指定路径，支持断点重试和临时文件安全写入

    :param url: 文件下载 URL
    :param dest_path: 目标路径（可以是目录或文件路径）
    :param max_retries: 最大重试次数
    :param exist_ok: 如果文件存在是否跳过下载
    :param temp_dir: 临时文件目录（默认使用系统临时目录）
    :param chunk_size: 下载分块大小
    :param verbose: 是否打印日志
    :return: 是否下载成功
    """
    # 处理临时目录
    temp_dir = temp_dir or tempfile.gettempdir()
    os.makedirs(temp_dir, exist_ok=True)

    if os.path.isdir(dest_path):
        filename = get_filename_from_url(url)
        if filename != "":
            dest_path = os.path.join(dest_path, filename)

    # 检查目标文件是否存在
    if os.path.exists(dest_path):
        if os.path.isfile(dest_path) and exist_ok:
            if verbose:
                cpcyan(f"[跳过] 文件已存在: {dest_path}")
            return dest_path
        elif os.path.isdir(dest_path):
            pass  # 后续处理目录
        else:
            if verbose:
                cpred(f"[错误] 路径错误: {dest_path} 不是文件或目录")
            return None

    # 重试逻辑（指数退避）
    retry_delay = 1  # 初始延迟 1 秒
    for attempt in range(max_retries):
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            # 确定最终文件路径
            if os.path.isdir(dest_path):
                filename = get_filename_from_response(response, url)
                final_filepath = os.path.join(dest_path, filename)
                os.makedirs(dest_path, exist_ok=True)
            else:
                final_filepath = dest_path
                os.makedirs(os.path.dirname(final_filepath), exist_ok=True)

            # 使用临时文件安全写入
            with tempfile.NamedTemporaryFile(dir=temp_dir, delete=False, prefix="download_") as tmp_file:
                temp_filepath = tmp_file.name
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        tmp_file.write(chunk)
                tmp_file.flush()  # 确保数据写入磁盘
                os.fsync(tmp_file.fileno())  # 强制同步（重要！）

            # 执行安全替换
            safe_replace(temp_filepath, final_filepath)
            if verbose:
                cpgreen(f"[成功] 下载完成: {final_filepath}")
            return final_filepath

        except HTTPError as e:
            if e.response.status_code == 404:
                if verbose:
                    cpred(f"[失败] 文件不存在: {url}")
                return None
            if verbose:
                cporange(f"[重试 {attempt+1}/{max_retries}] HTTP 错误: {e}")
        except (RequestException, IOError) as e:
            if verbose:
                cporange(f"[重试 {attempt+1}/{max_retries}] 错误: {e}")
        # 指数退避等待
        time.sleep(retry_delay)
        retry_delay *= 2

    if verbose:
        cpred(f"[失败] 超过最大重试次数: {url}")
    return None


def download_batch(
    urls: List[str],
    filenames: Optional[List[str]] = None,
    dest_path: Optional[str] = None,
    num_workers: int = 8,
    max_retries: int = 3,
    exist_ok: bool = True,
    temp_dir: Optional[str] = None,
    chunk_size: int = 8192,
    verbose: bool = True,
    progress_bar: bool = False,
) -> dict:
    """
    批量下载文件（支持多线程并发、断点续传、进度条）

    :param urls: 下载 URL 列表
    :param filenames: 对应的文件名列表（长度需与 urls 一致）
    :param dest_path: 目标路径（目录或文件路径模板）
    :param num_workers: 并发线程数
    :param max_retries: 单文件最大重试次数
    :param exist_ok: 是否跳过已存在的文件
    :param temp_dir: 临时文件目录
    :param chunk_size: 下载分块大小
    :param verbose: 是否显示详细日志
    :param progress_bar: 是否显示进度条

    :return: 结果字典 {
        "failed_urls": List[str],           # 失败的 URL
        "failed_indices": List[int],        # 失败的索引
        "failed_filenames": List[str],      # 失败的文件名
        "successful_urls": List[str],       # 成功的 URL
        "successful_indices": List[int],    # 成功的索引
        "successful_filepaths": List[str],  # 成功的文件路径
        "total": int,                       # 总任务数
        "success": int,                     # 成功数
        "status": bool                      # 是否全部成功
    }
    """
    # 参数校验
    if not urls:
        return {
            "failed_urls": [],
            "failed_indices": [],
            "failed_filenames": [],
            "successful_urls": [],
            "successful_indices": [],
            "successful_filepaths": [],
            "total": 0,
            "success": 0,
            "status": True,
        }

    if filenames and len(urls) != len(filenames):
        raise ValueError("urls 和 filenames 长度必须一致")

    # 确定目标路径和最终文件路径列表
    dest_path = dest_path or os.getcwd()
    final_paths = []

    if filenames:
        # 如果指定了 filenames，则 dest_path 作为目录
        os.makedirs(dest_path, exist_ok=True)
        for filename in filenames:
            final_path = os.path.join(dest_path, filename)
            final_paths.append(final_path)
    else:
        # 如果没有 filenames，则每个 URL 单独处理（自动获取文件名）
        os.makedirs(dest_path, exist_ok=True)
        final_paths = [dest_path] * len(urls)

    # 进度条配置
    disable_progress = not progress_bar

    # 准备任务参数列表
    tasks = []
    for idx, (url, path) in enumerate(zip(urls, final_paths)):
        tasks.append(
            {
                "url": url,
                "dest_path": path,
                "index": idx,
                "filename": filenames[idx] if filenames else None,
            }
        )

    # 执行并发下载
    failed_urls = []
    failed_indices = []
    failed_filenames = []
    successful_urls = []
    successful_indices = []
    successful_filepaths = []
    success_count = 0

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {
            executor.submit(
                download_file,
                task["url"],
                task["dest_path"],
                max_retries=max_retries,
                exist_ok=exist_ok,
                temp_dir=temp_dir,
                chunk_size=chunk_size,
                verbose=verbose,
            ): task
            for task in tasks
        }

        # # 使用 tqdm 进度条
        # with tqdm(
        #     total=len(tasks), disable=disable_progress, desc="下载进度", unit="文件"
        # ) as pbar:
        # 使用 Rich 进度条
        with RichProgress(total=len(tasks), desc="下载进度", disable=disable_progress) as pbar:
            for future in as_completed(futures):
                task = futures[future]
                try:
                    result = future.result()
                    if result:
                        successful_urls.append(task["url"])
                        successful_indices.append(task["index"])
                        successful_filepaths.append(result)
                        success_count += 1
                    else:
                        failed_urls.append(task["url"])
                        failed_indices.append(task["index"])
                        if task["filename"]:
                            failed_filenames.append(task["filename"])
                except Exception as e:
                    failed_urls.append(task["url"])
                    failed_indices.append(task["index"])
                    if task["filename"]:
                        failed_filenames.append(task["filename"])
                finally:
                    pbar.update(1)

    # 自动修复未指定 filenames 时的实际存储路径
    if not filenames:
        actual_filenames = []
        for url, path in zip(urls, final_paths):
            if os.path.exists(path):
                actual_filenames.append(os.path.basename(path))
            else:
                actual_filenames.append(os.path.basename(urlparse(url).path))
        failed_filenames = [actual_filenames[i] for i in failed_indices]

    result = {
        "failed_urls": failed_urls,
        "failed_indices": failed_indices,
        "failed_filenames": failed_filenames,
        "successful_urls": successful_urls,
        "successful_indices": successful_indices,
        "successful_filepaths": successful_filepaths,
        "total": len(urls),
        "success": success_count,
        "status": len(failed_urls) == 0,
    }
    if len(failed_urls) != 0:
        # sort failed_indices, and re-order failed_urls and failed_filenames
        failed_indices, failed_urls, failed_filenames = zip(*sorted(zip(failed_indices, failed_urls, failed_filenames)))
        result["failed_urls"] = list(failed_urls)
        result["failed_indices"] = list(failed_indices)
        result["failed_filenames"] = list(failed_filenames)
    if len(successful_urls) != 0:
        # sort successful_indices, and re-order successful_urls and successful_filepaths
        successful_indices, successful_urls, successful_filepaths = zip(
            *sorted(zip(successful_indices, successful_urls, successful_filepaths))
        )
        result["successful_urls"] = list(successful_urls)
        result["successful_indices"] = list(successful_indices)
        result["successful_filepaths"] = list(successful_filepaths)

    if verbose:
        if result["status"] == False:
            cporange(f"下载结果: 总计 {len(urls)} 个任务, {success_count} 个成功, {len(failed_urls)} 个失败")
        else:
            cpgreen(f"下载结果: 总计 {len(urls)} 个任务, {success_count} 个成功, {len(failed_urls)} 个失败")
    return result


def parallel_process(
    func: Callable,
    args_list: Iterable[Union[tuple, list, dict]],
    desc: Optional[str] = None,
    num_workers: int = 8,
    verbose: bool = False,
    progress_bar: bool = False,
    raise_exception: bool = True,
    ordered: bool = True,
) -> List:
    """
    并发执行函数（支持多参数和进度条）

    :param func: 要执行的函数
    :param args_list: 参数列表，每个元素是包含参数的元组/列表/字典
    :param description: 进度条描述
    :param num_workers: 并发线程数
    :param verbose: 是否打印详细日志
    :param progress_bar: 是否显示进度条
    :param raise_exception: 是否抛出异常
    :param ordered: 是否保持结果顺序

    :return: 结果列表（按参数顺序排列）
    """
    results = [None] * len(args_list) if ordered else []
    futures_map = {}

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # 提交所有任务
        for idx, args in enumerate(args_list):
            if isinstance(args, dict):
                future = executor.submit(func, **args)
            else:
                # 自动处理单参数情况
                call_args = args if isinstance(args, (tuple, list)) else (args,)
                future = executor.submit(func, *call_args)
            futures_map[future] = idx

        # 进度条配置
        with RichProgress(total=len(args_list), desc=desc or "执行进度", disable=not progress_bar) as pbar:
            # 处理完成的任务
            for future in as_completed(futures_map.keys()):
                idx = futures_map[future]
                try:
                    result = future.result()
                    if ordered:
                        results[idx] = result
                    else:
                        results.append(result)
                except Exception as e:
                    if verbose:
                        print(f"任务 {idx} 失败: {str(e)}")
                    if ordered:
                        results[idx] = e if not raise_exception else None
                    else:
                        results.append(e if not raise_exception else None)
                    if raise_exception:
                        raise e
                finally:
                    pbar.update(1)

    return results


def unzip_single_file(
    zip_path,
    intra_filename,
    new_filename: Optional[str] = None,
    save_dir: Optional[str] = None,
    force: bool = False,
) -> Optional[str]:
    """解压缩单个文件"""
    if not os.path.exists(zip_path):
        cpred(f"文件不存在: {zip_path}")
        return None

    if not force and os.path.exists(os.path.join(save_dir, new_filename or intra_filename)):
        cpcyan(f"文件已存在: {new_filename or intra_filename}")
        return os.path.join(save_dir, new_filename or intra_filename)

    if save_dir is None:
        save_dir = os.path.dirname(zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extract(intra_filename, save_dir)
    if new_filename is not None:
        safe_replace(os.path.join(save_dir, intra_filename), os.path.join(save_dir, new_filename))
    return os.path.join(save_dir, intra_filename) if new_filename is None else os.path.join(save_dir, new_filename)


def get_filename(
    filepath,
    new_extension: Optional[str] = None,
) -> str:
    """替换文件扩展名"""
    # 检查 filepath 是否是 url
    if "://" in filepath:
        filepath = urlparse(filepath).path
    if new_extension is None:
        return os.path.basename(filepath)
    new_extension = new_extension.strip()
    if new_extension == ".":
        raise ValueError("new_extension cannot be '.'")
    if not new_extension.startswith(".") and new_extension != "":
        new_extension = "." + new_extension
    return os.path.basename(filepath).rsplit(".", 1)[0] + new_extension


def replace_extension(filepath, new_extension: str) -> str:
    """替换文件扩展名"""
    new_extension = new_extension.strip()
    if not new_extension.startswith(".") and new_extension != "":
        new_extension = "." + new_extension
    return os.path.splitext(filepath)[0] + new_extension


import imghdr
import magic
import pybase64
import mimetypes


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


if __name__ == "__main__":
    if True:
        start = time.perf_counter()
        save_base64_data(open("./test/base64_test1.txt", "r").read(), output_dir="./test", filename="test1")
        print("耗时:", time.perf_counter() - start)
        start = time.perf_counter()
        save_base64_data(open("./test/base64_test2.txt", "r").read(), output_dir="./test", filename="test2")
        print("耗时:", time.perf_counter() - start)

    if False:
        # 测试日期范围生成
        from pprint import pprint

        print("测试: 2023-02-01 到 2023-02-05")
        pprint(list_date("2023-02-01", "2023-02-05"))
        print("测试: 2025-01-01 到 2025-02-10 按周")
        pprint(list_date("2025-02-01", "2025-02-10", step="week"))
        print("测试: 1999-02-01 到 2000-01-07 按月")
        pprint(list_date("1999-02-01", "2000-01-07", step="month"))
        print("测试: 1995-02-01 到 2000-01-07 按年")
        pprint(list_date("1995-02-01", "2000-01-07", step="year"))

        print("测试: 2023-02-01 到 2023-02-05")
        for i in range_date("2023-02-01", "2023-02-5"):
            print(i)
        print("测试: 2025-01-07 到 2025-02-10 按周")
        for i in range_date("2025-01-07", "2025-02-10", step="week"):
            print(i)
        print("测试: 1999-02-11 到 2000-01-07 按月")
        for i in range_date("1999-02-11", "2000-01-31", step="month"):
            print(i)
        print("测试: 1995-02-01 到 2000-01-07 按年")
        for i in range_date("1995-02-01", "2000-01-07", step="year"):
            print(i)

    if False:
        # 测试 get_filename
        print(get_filename("https://example.com/test.zip"))
        print(get_filename("https://example.com/test.zip", ""))
        print(get_filename("https://example.com/test.zip", "csv"))
        print(get_filename("https://example.com/test.zip", ".csv"))
        print(get_filename("C:/Users/abc/test.zip"))
        print(get_filename("C:/Users/abc/test.zip", "csv"))

    if False:
        # 并发计算示例
        def square(x):
            cpblue(f"计算平方: {x}")
            time.sleep(1)
            return x * x

        print(parallel_process(square, range(10), "计算平方", num_workers=100, progress_bar=True))

        # 测试函数
        def test_func(a, b=0):
            print(f"参数 a: {a}, b: {b}")
            time.sleep(1)
            return a + b

        # 单参数模式
        print(parallel_process(test_func, [(1,), (2,), (3,)], progress_bar=True))

        # 多参数模式
        print(parallel_process(test_func, [(1, 2), (3, 4), (5, 6)], progress_bar=True))

        # 混合参数模式
        print(parallel_process(test_func, [1, (2, 3), {"a": 5, "b": 6}], progress_bar=True))  # 自动转换参数类型

    if False:
        print(list_date("2023-01-01", "2023-01-10"))

        for i in range_date("2023-01-01", "2023-01-10"):
            print(i)

    if False:
        # 批量下载示例
        def build_okx_url(date_obj):
            exchange_symbol = "ETH-USDT"
            yyyymmdd = date_obj.strftime("%Y%m%d")
            yyyy_mm_dd = date_obj.strftime("%Y-%m-%d")
            return f"https://www.okx.com/cdn/okex/traderecords/trades/daily/{yyyymmdd}/{exchange_symbol}-trades-{yyyy_mm_dd}.zip"

        import pandas as pd
        from pprint import pprint

        urls = [build_okx_url(date) for date in pd.date_range("2023-01-01", "2023-01-10")]

        if False:
            is_url_exists_batch(urls, verbose=True, progress_bar=True)

        res = download_batch(
            urls,
            dest_path="./test",
            num_workers=4,
            progress_bar=True,
        )
        pprint(res)
        # 解压缩示例
        for file in res["successful_filepaths"]:
            if not os.path.exists(replace_extension(file, "csv")):
                unzip_single_file(
                    file,
                    get_filename(file, "csv"),
                    new_filename=get_filename(file, "csv"),
                )
                cpgreen(f"解压缩成功: {file}")
            else:
                cpcyan(f"文件已存在: {replace_extension(file, 'csv')}")
        csv_files = [replace_extension(file, "csv") for file in res["successful_filepaths"]]

        results = [None] * len(csv_files)
        for i, file in RichProgress(enumerate(csv_files), total=len(csv_files), desc="导入DolphinDB"):
            results[i] = import_csv_to_dolphindb(
                csv_path=os.path.abspath(file), db_name="testDB", table_name="testTable"
            )
        cpgreen(f"导入成功: {results}")

    if False:
        myconfig = JsonDict("test.json", "rw")
        myconfig["d"] = 100000
        myconfig["list"] = [1, 2, 3]
        myconfig["dict"] = {"a": 1, "b": 2}
        print(myconfig)
        # myconfig = YamlDict("test.yaml")
        # myconfig["d"] = 4
        # myconfig["list"] = [1, 2, 3]
        # myconfig["dict"] = {"a": 1, "b": 2}

    if False:
        cpgreen("Hello")
        cpred("Hello")
        cpblue("Hello")
        cpyellow("Hello")
        cporange("Hello")
        cppurple("Hello")
        cpcyan("Hello")
        cpgrey("Hello")
        cpbold("Hello")
        cpunderline("Hello")
        cpitalic("Hello")
        cpstrikethrough("Hello")

    if False:
        loading = LoadingAnimation("Loading")
        time.sleep(3)
        loading.stop()
        loading = LoadingAnimation("Loading", "spinner")
        time.sleep(3)
        loading.stop()

    if False:

        selections = ["选项1", "选项2", "选项3"]
        print(select("请选择一个选项", selections, 1, True))
        print(confirm("是否继续", False))
        print(multi_select("请选择多个选项", selections, [0, 2], True))
        print(password(correct_password="123"))
        print(password(validater=lambda text: len(text) >= 6 or "密码长度必须大于等于 6"))
        print(input("请输入文本", "默认文本"))
        print(input("请输入多行文本", multiline=True).replace("\n", "\\n"))
        questions = [
            {
                "type": "select",
                "message": "请选择一个选项",
                "selections": selections,
                "default": 1,
                "return_index": False,
                "skip": False,
            },
            {
                "type": "confirm",
                "message": "是否继续",
                "default": False,
                "skip": False,
            },
        ]
        print(prompt(questions))

    cporange("\nUnit test done. Have a nice day!\n")
    confirm("是否继续")
    cpclear()
