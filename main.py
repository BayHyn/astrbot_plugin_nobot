import asyncio
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import At, Forward, Image, Plain, Record, Reply, Video
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.filter.event_message_type import EventMessageType
import astrbot.api.message_components as Comp
from astrbot.api.event import filter
from .manager import BotManager
from astrbot.core.utils.session_waiter import (
    session_waiter,
    SessionController,
)
from astrbot import logger


@register(
    "astrbot_plugin_nobot",
    "Zhalslar",
    "找出并禁言群里的人机!",
    "1.0.3",
    "https://github.com/Zhalslar/astrbot_plugin_nobot",
)
class NobotPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 测试人机用的命令列表
        self.test_cmds: list[str] = config.get("test_cmds", ["/help"])
        # 测试命令发送的时间间隔(秒)
        self.test_interval: int = config.get("test_interval", 2)
        # 找人机命令执行中，用户消息包含以下字符会被标记为人机
        self.bot_words: list[str] = config.get("bot_words", [])
        # 人机发言间隔限制（秒）
        self.speak_threshold: int = config.get("speak_threshold", 20)
        # 消息最大长度
        self.max_length: int = config.get("max_length", 150)
        # 禁言时长（秒）
        self.ban_duration: int = config.get("ban_duration", 1800)
        # 禁言时是否同时撤回消息
        self.is_delete_msg: bool = config.get("is_delete_msg", True)
        # 通融时间
        self.ban_sleep = config.get("ban_sleep", 3)
        # 监控人机的群聊
        self.monitoring_groups: list[str] = config.get("monitoring_groups", [])
        # 人机数据
        bot_data_list: list[dict] = config.get("bot_data_list", {})
        bot_data = bot_data_list[0] if bot_data_list else {}
        # 人机管理器
        self.bm = BotManager(bot_data, config)
        # 忽略的命令
        self.ignore_cmds = config.get("ignore_cmds", [])

    @staticmethod
    async def _get_name(event: AstrMessageEvent, user_id: str | int):
        """从消息平台获取用户昵称"""
        if event.get_platform_name() == "aiocqhttp":
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )

            assert isinstance(event, AiocqhttpMessageEvent)
            client = event.bot
            group_id = event.get_group_id()
            user_info = await client.get_group_member_info(
                group_id=int(group_id), user_id=int(user_id)
            )
            return user_info.get("card") or user_info.get("nickname")
        # TODO 适配更多消息平台

    @staticmethod
    def get_ats(event: AstrMessageEvent) -> list[str]:
        """获取被at者们的id列表"""
        messages = event.get_messages()
        self_id = event.get_self_id()
        return [
            str(seg.qq)
            for seg in messages
            if (isinstance(seg, Comp.At) and str(seg.qq) != self_id)
        ]

    @staticmethod
    async def ban(event: AstrMessageEvent, user_id: str | int, duration: int = 0):
        """禁言/解禁"""
        if event.get_platform_name() == "aiocqhttp":
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )

            assert isinstance(event, AiocqhttpMessageEvent)
            client = event.bot
            group_id = event.get_group_id()
            try:
                await client.set_group_ban(
                    group_id=int(group_id),
                    user_id=int(user_id),
                    duration=duration,
                )
            except:  # noqa: E722
                return

    @staticmethod
    async def delete_msg(event: AstrMessageEvent):
        """撤回消息"""
        if event.get_platform_name() == "aiocqhttp":
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )

            assert isinstance(event, AiocqhttpMessageEvent)
            client = event.bot
            message_id = event.message_obj.message_id
            try:
                await client.delete_msg(message_id=int(message_id))
            except:  # noqa: E722
                return

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("开启人机禁言")
    async def start_ban(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        self.monitoring_groups.append(group_id)
        yield event.plain_result("本群已开启人机禁言")
        self.config.save_config()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("关闭人机禁言")
    async def stop_ban(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        self.monitoring_groups.remove(group_id)
        yield event.plain_result("本群已关闭人机禁言")
        self.config.save_config()

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("标记人机", alias={"杀"})
    async def label_bot(self, event: AstrMessageEvent):
        """标记人机"""
        group_id = event.get_group_id()
        bot_ids = self.get_ats(event)

        for bot_id in bot_ids:
            is_success = self.bm.add_bot_record(group_id, bot_id)
            if is_success:
                bot_name = await self._get_name(event, bot_id)
                yield event.plain_result(f"已将【{bot_name}】标记为人机")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("取消标记", alias={"救"})
    async def unlabel_bot(self, event: AstrMessageEvent):
        """取消人机标记"""
        group_id = event.get_group_id()
        bot_ids = self.get_ats(event)

        for bot_id in bot_ids:
            self.bm.remove_bot_record(group_id, bot_id)
            await self.ban(event, bot_id, 0)
            bot_name = await self._get_name(event, bot_id)
            yield event.plain_result(f"已取消【{bot_name}】的人机标记")

    @filter.command("人机列表")
    async def bot_list(self, event: AstrMessageEvent):
        """人机列表"""
        group_id = event.get_group_id()
        bot_ids = self.bm.get_bot_ids(group_id)
        bot_names = await asyncio.gather(
            *[self._get_name(event, bot_id) for bot_id in bot_ids]
        )
        yield event.plain_result(f"{bot_names}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("找人机")
    async def handle_empty_mention(self, event: AstrMessageEvent):
        """找出群里的人机"""
        timeout = self.test_interval * (len(self.test_cmds) + 1)

        @session_waiter(timeout=timeout, record_history_chains=False)  # type: ignore
        async def empty_mention_waiter(
            controller: SessionController, event: AstrMessageEvent
        ):
            chain = event.get_messages()
            message_str = event.message_str
            group_id = event.get_group_id()
            user_id = event.get_sender_id()
            bot_name = await self._get_name(event, user_id)

            reply = f"{bot_name}别乱发消息，小心被标成人机"

            if chain and isinstance(chain[0], Comp.Reply):
                self.bm.add_bot_record(group_id, user_id)
                reply = f"【{bot_name}】合并转发了消息，已标记为人机"

            elif len(message_str) > self.max_length:
                self.bm.add_bot_record(group_id, user_id)
                reply = f"【{bot_name}】话太多了，已标记为人机"

            elif message_str:
                for word in self.bot_words:
                    if word in message_str:
                        self.bm.add_bot_record(group_id, user_id)
                        bot_name = await self._get_name(event, user_id)
                        reply = f"【{bot_name}】言语中含有人机特征，已标记为人机"
                        break

            message_result = event.make_result()
            message_result.chain = [Comp.Plain(reply)]
            await event.send(message_result)

            controller.keep(timeout=0, reset_timeout=False)

        async def run_empty_mention_waiter():
            try:
                await empty_mention_waiter(event)
            except TimeoutError as _:
                message_result = event.make_result()
                message_result.chain = [Comp.Plain("找完了")]
                await event.send(message_result)
            except Exception as e:
                logger.error("handle_empty_mention error: " + str(e))
            finally:
                event.stop_event()

        async def run_test_cmds():
            for cmd in self.test_cmds:
                message_result = event.make_result()
                message_result.chain = [Comp.Plain(f"{cmd}")]
                await event.send(message_result)
                await asyncio.sleep(self.test_interval)

        await asyncio.gather(run_empty_mention_waiter(), run_test_cmds())

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def handle_msg(self, event: AstrMessageEvent):
        """强制控制人机发言"""
        raw_message = getattr(event.message_obj, "raw_message", None)

        if not (
            raw_message
            and isinstance(raw_message, dict)
            and event.message_obj.message
            and isinstance(
                event.message_obj.message[0], (Plain, Image, Record, Video, Forward, Reply, At)
            )
        ):
            return

        role = raw_message.get("sender", {}).get("role")
        if role in ["owner", "admin"]:
            return

        group_id = event.get_group_id()
        sender_id = event.get_sender_id()
        # 检查群聊是否在监控列表中以及用户是否为人机
        if (
            group_id not in self.monitoring_groups
            or group_id not in self.bm.get_groups()
            or sender_id not in self.bm.get_bot_ids(group_id)
        ):
            return

        # 通融机制
        chain = event.get_messages()
        if chain and isinstance(chain[0], Comp.At):
            await asyncio.sleep(self.ban_sleep)

        # 检查消息长度
        if len(event.message_str) > self.max_length:
            yield event.plain_result("干嘛发这么长的文本！")
            if self.is_delete_msg:
                await self.delete_msg(event)
            await self.ban(event, sender_id, self.ban_duration)
            return

        # 检查发言频率、同时更新发言时间
        if self.bm.check_speak_frequency(group_id, sender_id, self.speak_threshold):
            event.stop_event()
            if self.is_delete_msg:
                await self.delete_msg(event)
            await self.ban(event, sender_id, self.ban_duration)
            return

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=99)
    async def on_waking(self, event: AstrMessageEvent):
        """收到消息后的预处理"""
        # 屏蔽特定指令
        print(event.message_str)
        print(self.ignore_cmds)
        if not event.is_admin() and event.message_str in self.ignore_cmds:
            event.stop_event()
            return
