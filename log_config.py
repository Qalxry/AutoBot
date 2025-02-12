import os
import time
import logging
from logging.handlers import RotatingFileHandler


class CustomFormatter(logging.Formatter):
    """Logging colored formatter, adapted from https://stackoverflow.com/a/56944256/3638629"""

    grey = "\033[90m"
    cyan = "\033[36m"
    yellow = "\033[33m"
    red = "\033[31m"
    bold = "\033[1m"
    bg_white = "\033[47m"
    reset = "\033[0m"

    def __init__(self, fmt, datefmt):
        super().__init__()
        self.fmt = fmt
        self.datefmt = datefmt
        self.FORMATS = {
            logging.DEBUG: self.bold + self.grey + self.fmt + self.reset,
            logging.INFO: self.cyan + self.fmt + self.reset,
            logging.WARNING: self.yellow + self.fmt + self.reset,
            logging.ERROR: self.red + self.fmt + self.reset,
            logging.CRITICAL: self.bg_white + self.bold + self.red + self.fmt + self.reset,
        }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt=self.datefmt)
        return formatter.format(record)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 创建一个日志记录器
logger_fmt = "[%(asctime)s][%(levelname)s][%(module)s::%(funcName)s] %(message)s"
logger_date_fmt = "%Y-%m-%d %H:%M:%S"
logger = logging.getLogger("autobot")
logger.setLevel(logging.DEBUG)

# 创建彩色终端输出处理器（StreamHandler）
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(CustomFormatter(fmt=logger_fmt, datefmt=logger_date_fmt))

# # 创建文件输出处理器（FileHandler）
# file_handler = RotatingFileHandler(
#     os.path.join(LOG_DIR, "autobot.log"),
#     mode="a",
#     maxBytes=10 * 1024 * 1024,  # 10 MB
#     backupCount=5,
#     encoding="utf-8",
# )
file_handler = logging.FileHandler(
    os.path.join(LOG_DIR, "autobot.log"),
    mode="w",
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(fmt=logger_fmt, datefmt=logger_date_fmt))

# 将处理器添加到日志记录器
logger.addHandler(stream_handler)
logger.addHandler(file_handler)


def set_logger_level(level: str):
    """
    设置日志级别
    :param level: 日志级别
    """
    logger.setLevel(level)
    stream_handler.setLevel(level)
    file_handler.setLevel(level)


# 示例函数用于测试日志输出中的函数名称
def sample_function():
    set_logger_level(logging.DEBUG)
    logger.debug("This is a log message from sample_function.")
    logger.info("This is a log message from sample_function.")
    logger.warning("This is a log message from sample_function.")
    logger.error("This is a log message from sample_function.")
    logger.critical("This is a log message from sample_function.")
    set_logger_level(logging.INFO)
    logger.debug("This is a log message from sample_function.")
    logger.info("This is a log message from sample_function.")
    logger.warning("This is a log message from sample_function.")
    logger.error("This is a log message from sample_function.")
    logger.critical("This is a log message from sample_function.")


class TestClass:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def test_method(self):
        set_logger_level(logging.DEBUG)
        logger.debug("This is a log message from sample_function.")
        logger.info("This is a log message from sample_function.")
        logger.warning("This is a log message from sample_function.")
        logger.error("This is a log message from sample_function.")
        logger.critical("This is a log message from sample_function.")
        set_logger_level(logging.INFO)
        logger.debug("This is a log message from sample_function.")
        logger.info("This is a log message from sample_function.")
        logger.warning("This is a log message from sample_function.")
        logger.error("This is a log message from sample_function.")
        logger.critical("This is a log message from sample_function.")


if __name__ == "__main__":
    sample_function()
    TestClass().test_method()
