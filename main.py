import asyncio
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.filter.event_message_type import EventMessageType
import astrbot.api.message_components as Comp
from astrbot.api.event import filter
from .manager import BotManager


@register(
    "astrbot_plugin_nobot",
    "Zhalslar",
    "人机去死！找出并禁言群里的人机!",
    "1.0.0",
    "https://github.com/Zhalslar/astrbot_plugin_nobot",
)
class NobotPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 人机数据
        bot_data_list: list[dict] = config.get("bot_data_list", {})
        bot_data = bot_data_list[0] if bot_data_list else {}
        # 人机管理器
        self.bm = BotManager(bot_data, config)
        # 测试人机用的命令列表
        self.test_cmds: list[str] = config.get("test_cmds", ["/help"])
        # 测试命令发送的时间间隔(秒)
        self.test_interval: int = config.get("test_interval", 2)
        # 人机被at或被reply时，禁言程序进入睡眠的时长
        self.ban_sleep: int = config.get("ban_sleep", 3)
        # 找人机命令执行中，用户消息包含以下字符会被标记为人机
        self.bot_words: list[str] = config.get("bot_words", [])
        # 发言间隔限制（秒）
        self.speak_threshold: int = config.get("speak_threshold", 20)
        # 消息最大长度
        self.max_length: int = config.get("max_length", 150)
        # 禁言时长（秒）
        self.ban_duration: int = config.get("ban_duration", 1800)

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
        """执行禁言并撤回的操作"""
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
        """执行禁言并撤回的操作"""
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

    @filter.command("开启人机禁言")
    async def start_ban(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        self.bm.toggle_ban(group_id, True)
        yield event.plain_result("已开启人机禁言")

    @filter.command("关闭人机禁言")
    async def stop_ban(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        self.bm.toggle_ban(group_id, False)
        yield event.plain_result("已关闭人机禁言")

    @filter.command("标记人机")
    async def label_bot(self, event: AstrMessageEvent):
        """标记人机"""
        group_id = event.get_group_id()
        bot_ids = self.get_ats(event)

        for bot_id in bot_ids:
            is_success = self.bm.add_bot_record(group_id, bot_id)
            if is_success:
                bot_name = await self._get_name(event, bot_id)
                yield event.plain_result(f"已将【{bot_name}】标记为人机")

    @filter.command("取消标记",alias={"救"})
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

    @filter.command("找人机")
    async def find_bot(self, event: AstrMessageEvent):
        group_id = event.get_group_id()
        self.bm._get_or_create_group(group_id)
        # 重复触发则停止
        if self.bm.is_monitoring(group_id):
            self.bm.toggle_monitoring(group_id, False)
            yield event.plain_result("催什么催！不找了！")
        # 启动监控
        self.bm.toggle_monitoring(group_id, True)
        for cmd in self.test_cmds:
            if self.bm.is_monitoring(group_id) is False:
                return
            yield event.plain_result(cmd)
            await asyncio.sleep(self.test_interval)
        self.bm.toggle_monitoring(group_id, False)
        yield event.plain_result("找完了")

    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def meme_handle(self, event: AstrMessageEvent):
        """找人机时，监控谁是人机"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        if not self.bm.is_monitoring(group_id):
            return

        message_str = event.get_message_str()
        if len(message_str) > self.max_length:
            self.bm.add_bot_record(group_id, user_id)
            bot_name = await self._get_name(event, user_id)
            yield event.plain_result(f"【{bot_name}】话太多了，已标记为人机")
        else:
            for word in self.bot_words:
                if word in message_str:
                    self.bm.add_bot_record(group_id, user_id)
                    bot_name = await self._get_name(event, user_id)
                    yield event.plain_result(f"【{bot_name}】言语中含有人机特征，已标记为人机")


    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def handle_msg(self, event: AstrMessageEvent):
        """强制控制人机发言"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()

        # 检查用户是否在当前群聊的人机列表中
        if group_id not in self.bm.get_groups() or user_id not in self.bm.get_bot_ids(
            group_id
        ):
            return

        # 检查消息长度
        message_str = event.get_message_str()
        if len(message_str) > self.max_length:
            yield event.plain_result("干嘛发这么长的文本！")
            await self.delete_msg(event)
            await self.ban(event,user_id, self.ban_duration)
            return

        # 检查发言频率、同时更新发言时间
        if self.bm.check_speak_frequency(group_id, user_id, self.speak_threshold):
            event.stop_event()
            await self.delete_msg(event)
            await self.ban(event,user_id, self.ban_duration)
            return
