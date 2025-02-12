import json
import time
import asyncio
import websockets
from typing import Callable, Literal, Optional, Dict
from log_config import logger
from notify_auto import qq_send_message, get_event
from tui import recursive_update


def register_action(name: str = None):
    def decorator(func: Callable):
        # 标记方法为待注册动作
        func._is_action = True
        func._action_name = name or func.__name__
        return func

    return decorator


class ReverseWebSocketProtocol:
    def __init__(self, uri, bot_qid, reconnect_delay=5, ping_interval=20, ping_timeout=10):
        self.uri = uri
        self.bot_qid = bot_qid
        self.reconnect_delay = reconnect_delay
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.registered_actions: Dict[str, Callable] = {}
        self._register_actions()

    def _register_actions(self):
        # 通过类和方法名反射获取被装饰的方法
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if hasattr(attr, "_is_action"):
                action_name = getattr(attr, "_action_name", attr_name)
                self.registered_actions[action_name] = attr

    def execute_action(self, name: str, *args, **kwargs):
        """
        根据名称执行注册的动作。这里需要注意，注册的动作在类中是未绑定方法，
        调用时需要传递实例 self 作为第一个参数。
        """
        if name in self.registered_actions:
            return self.registered_actions[name](*args, **kwargs)
        else:
            return {"retcode": 1404, "message": "Unsupported action: " + name}

    def build_response(
        self,
        data: dict = None,
        status: Literal["ok", "failed"] = "ok",
        retcode: Literal["0", "1400", "1401", "1403", "1404"] = "0",
        message: str = "",
        wording: str = "",
        echo: str = "",
    ):
        retcode = str(retcode)
        if retcode == "0":
            status = "ok"
        else:
            status = "failed"
        res = {
            "status": status,
            "retcode": int(retcode),
            "data": data,
            "message": message,
            "wording": wording,
            "echo": echo,
        }
        if status == "failed":
            logger.warning(f"失败：{res}")
        return json.dumps(res)

    def parse_request(self, req: dict):
        logger.debug(f"解析请求：{req}")
        action = req.get("action", "")
        params = req.get("params", {})
        echo = req.get("echo", "")
        response = self.execute_action(action, params)
        return self.build_response(**response, echo=echo)

    def build_event_lifetime(
        self,
        sub_type: Literal["enable", "disable", "connect"],
    ):
        return json.dumps(
            {
                "time": int(time.time()),
                "self_id": int(self.bot_qid),
                "post_type": "meta_event",
                "meta_event_type": "lifecycle",
                "sub_type": sub_type,
            }
        )

    def build_event_heartbeat(self):
        return json.dumps(
            {
                "time": int(time.time()),
                "self_id": int(self.bot_qid),
                "post_type": "meta_event",
                "meta_event_type": "heartbeat",
                "status": {"good": True, "online": True},
                "interval": self.ping_interval * 1000,
            }
        )

    def build_event_private_message(self, event: dict):
        base_event = {
            "time": int(time.time()),
            "self_id": int(self.bot_qid),
            "post_type": "message",
            "message_type": "private",
            "sub_type": "friend",
            "message_id": 0,
            "user_id": 0,
            "message": [],
            "raw_message": "",
            "font": 26,
            "sender": {
                "user_id": 0,
                "nickname": "",
                "sex": "unknown",
                "age": 0,
            },
        }
        recursive_update(base_event, event)
        return json.dumps(base_event)

    def parse_event_response_private_message(self, data: dict):
        """
        事件上报的后端可以在上报请求的响应中直接指定一些简单的操作，称为「快速操作」，如快速回复、快速禁言等。
        如果不需要使用这个特性，返回 HTTP 响应状态码 204，或保持响应正文内容为空；
        如果需要，则使用 JSON 作为响应正文，Content-Type 响应头任意（目前不会进行判断），
        但设置为 application/json 最好，以便减少不必要的升级成本，因为如果以后有需求，可能会加入判断。
        注意：无论是否需要使用快速操作，事件上报后端都应该在处理完毕后返回 HTTP 响应，否则 OneBot 将一直等待直到超时。
        """
        if data is None or data == {}:
            return
        logger.critical(f"暂不支持快速操作：{data}")

    def build_event_group_message(self, event: dict):
        base_event = {
            "time": int(time.time()),
            "self_id": int(self.bot_qid),
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "message_id": 0,
            "group_id": 0,
            "user_id": 0,
            "anonymous": None,
            "message": [],
            "raw_message": "",
            "font": 26,
            "sender": {
                "user_id": 0,
                "nickname": "",
                "card": "",
                "sex": "unknown",
                "age": 0,
                "area": "unknown",
                "level": "",
                "role": "",
                "title": "",
            },
        }
        # 将 base_event 递归更新为 event 中的内容
        recursive_update(base_event, event)
        return json.dumps(base_event)

    def parse_event_response_group_message(self, data: dict):
        if data is None or data == {}:
            return
        logger.critical(f"暂不支持快速操作：{data}")

    def send_message(self, message_type, id, message):
        if message_type not in ["private", "group"]:
            return {"retcode": 1400, "message": f"Unsupported message_type: {message_type}"}
        if not id:
            return {"retcode": 1400, "message": "user_id or group_id not provided"}
        if not message:
            return {"retcode": 1400, "message": "Request data is empty"}
        message_id = qq_send_message(message_type, id, message)
        if message_id is None:
            return {"retcode": 1401, "message": "Failed to send message"}
        return {"data": {"message_id": message_id}, "message": "Message sent successfully"}

    @register_action()
    def send_msg(self, data: dict):
        return self.send_message(
            message_type=data.get("message_type", ""),
            id=data.get("group_id", None) or data.get("user_id", ""),
            message=data.get("message", ""),
        )

    @register_action()
    def send_private_msg(self, data: dict):
        return self.send_message(
            message_type="private",
            id=data.get("user_id", ""),
            message=data.get("message", ""),
        )

    @register_action()
    def send_group_msg(self, data: dict):
        return self.send_message(
            message_type="group",
            id=data.get("group_id", ""),
            message=data.get("message", ""),
        )

    @register_action()
    def get_status(self, data):
        return {"online": True, "good": True, "stat": {}}  # 返回状态

    @register_action()
    def can_send_image(self, data):
        return {"yes": True}


async def receive_messages(
    websocket: websockets.ClientConnection,
    adapter: ReverseWebSocketProtocol,
):
    logger.info("启动接收任务")
    try:
        async for request in websocket:
            logger.info(f"收到请求: {request}")
            req = json.loads(request)
            response = adapter.parse_request(req)
            logger.info(f"发送响应: {response}")
            await websocket.send(response)
    except websockets.exceptions.ConnectionClosed:
        logger.error("当前连接已关闭")
    except Exception as e:
        logger.error(f"接收消息时发生异常: {e}")


async def send_hearbeat(
    websocket: websockets.ClientConnection,
    adapter: ReverseWebSocketProtocol,
    interval: int = 20,
):
    logger.info(f"启动心跳任务，间隔：{interval} 秒")
    try:
        while True:
            await asyncio.sleep(interval)
            await websocket.send(adapter.build_event_heartbeat())
    except websockets.exceptions.ConnectionClosed:
        logger.error("当前连接已关闭")
    except Exception as e:
        logger.error(f"发送心跳时发生异常: {e}")


async def send_messages(
    websocket: websockets.ClientConnection,
    adapter: ReverseWebSocketProtocol,
):
    # 持续从命令行读取输入发送消息
    logger.info("Monitor 启动")
    try:
        while True:
            event = await get_event()
            if event:
                if event["post_type"] == "message" and event["message_type"] == "private":
                    event = adapter.build_event_private_message(event)
                    logger.info(f"发送消息：{event}")
                    await websocket.send(event)
                elif event["post_type"] == "message" and event["message_type"] == "group":
                    event = adapter.build_event_group_message(event)
                    logger.info(f"发送消息：{event}")
                    await websocket.send(event)
                else:
                    logger.error(f"未知事件类型：{event}")
            await asyncio.sleep(0.001)
    except websockets.exceptions.ConnectionClosed:
        logger.error("当前连接已关闭")
    except Exception as e:
        logger.error(f"发送消息时发生异常: {e}")


async def open_websocket(
    uri,
    bot_qid,
    reconnect_delay,
    ping_interval,
    ping_timeout,
):
    logger.info(f"启动反向 WebSocket 连接：{uri}")
    adapter = ReverseWebSocketProtocol(uri, bot_qid, reconnect_delay, ping_interval, ping_timeout)
    logger.info(f"已注册动作：{adapter.registered_actions.keys()}")
    async with websockets.connect(
        uri,
        additional_headers={
            "X-Self-ID": str(bot_qid),
            "X-Client-Role": "Universal",
            "User-Agent": "OneBot/11",
        },
        ping_interval=ping_interval,
        ping_timeout=ping_timeout,
    ) as ws:
        logger.info(f"反向 WebSocket 连接成功")
        # 发送 lifecycle 事件
        req = adapter.build_event_lifetime("connect")
        logger.info(f"发送生命周期事件: {req}")
        await ws.send(req)
        logger.info(f"已发送生命周期事件")

        # 同时启动接收、发送、心跳任务
        receive_task = asyncio.create_task(receive_messages(ws, adapter))
        send_task = asyncio.create_task(send_messages(ws, adapter))
        heartbeat_task = asyncio.create_task(send_hearbeat(ws, adapter, ping_interval))
        done, pending = await asyncio.wait(
            [receive_task, send_task, heartbeat_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        # 如果其中一个任务完成，则取消另一个任务
        for task in pending:
            task.cancel()


async def run_reverse_websocket(
    uri,
    bot_qid,
    reconnect_delay=5,
    ping_interval=20,
    ping_timeout=10,
):
    while True:
        try:
            await open_websocket(
                uri,
                bot_qid,
                reconnect_delay,
                ping_interval,
                ping_timeout,
            )
        except asyncio.TimeoutError as e:
            logger.error(f"超时，等待 {reconnect_delay} 秒后重连... {e}")
        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidStatusCode) as e:
            logger.error(f"连接异常，等待 {reconnect_delay} 秒后重连... {e}")
        except Exception as e:
            logger.error(f"其他异常，等待 {reconnect_delay} 秒后重连... {e}")
        await asyncio.sleep(reconnect_delay)


# async def run_reverse_websocket(
#     uri,
#     bot_qid,
#     reconnect_delay=5,
#     ping_interval=5,
#     ping_timeout=5,
# ):
#     """
#     GET /ws HTTP/1.1
#     Host: 127.0.0.1:8080
#     Connection: Upgrade
#     Upgrade: websocket
#     X-Self-ID: {bot_qid}
#     X-Client-Role: Universal
#     """
#     logger.info(f"启动 ReverseWebSocket 连接：{uri}")
#     while True:
#         try:
#             protocol = ReverseWebSocketProtocol(uri, bot_qid, reconnect_delay, ping_interval, ping_timeout)
#             start_time = time.time()
#             last_hb_time = start_time
#             async with websockets.connect(
#                 uri,
#                 additional_headers={
#                     "X-Self-ID": str(bot_qid),
#                     "x-client-role": "Universal",
#                     "User-Agent": "OneBot/11",
#                     "Authorization": f"Bearer ",
#                 },
#                 ping_interval=ping_interval,
#                 ping_timeout=ping_timeout,
#             ) as ws:
#                 logger.info(f"连接成功，耗时：{time.time() - start_time:.2f} 秒")
#                 req = protocol.build_event_lifetime("connect")
#                 logger.info(f"发送连接事件: {req}")
#                 await ws.send(req)

#                 while True:
#                     event = await get_event()
#                     if event:
#                         if event["post_type"] == "message" and event["message_type"] == "private":
#                             logger.info(f"发送消息：{event}")
#                             await ws.send(protocol.build_event_private_message(event))
#                             response = await ws.recv(decode=True)
#                             logger.info(f"收到响应：{response}")
#                             req = json.loads(response)
#                             protocol.parse_event_response_private_message(req)

#                         elif event["post_type"] == "message" and event["message_type"] == "group":
#                             logger.info(f"发送消息：{event}")
#                             await ws.send(protocol.build_event_group_message(event))
#                             response = await ws.recv(decode=True)
#                             logger.info(f"收到响应：{response}")
#                             req = json.loads(response)
#                             protocol.parse_event_response_group_message(req)
#                         else:
#                             logger.error(f"未知事件类型：{event}")

#                     # 检查是否需要发送心跳
#                     if time.time() - last_hb_time >= ping_interval:
#                         logger.info(f"发送心跳")
#                         await ws.send(protocol.build_event_heartbeat())
#                         last_hb_time = time.time()
#                         # response = await ws.recv(decode=True)
#                         # logger.info(f"收到心跳响应：{response}")

#                     # 检查是否收到对方的消息，如果有则处理
#                     response = await asyncio.wait_for(ws.recv(decode=True), timeout=ping_interval)
#                     logger.info(f"收到消息：{response}")
#                     req = json.loads(response)
#                     response = protocol.parse_request(req)
#                     await ws.send(response)
#                     response = await ws.recv(decode=True)
#                     logger.info(f"收到响应：{response}")

#         except asyncio.TimeoutError as e:
#             logger.error(f"心跳超时，等待 {reconnect_delay} 秒后重连... {e}")
#         except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidStatusCode) as e:
#             logger.error(f"连接异常，等待 {reconnect_delay} 秒后重连... {e}")
#         except Exception as e:
#             logger.error(f"其他异常，等待 {reconnect_delay} 秒后重连... {e}")
#         await asyncio.sleep(reconnect_delay)
