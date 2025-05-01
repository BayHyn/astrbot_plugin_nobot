from typing import Any, Dict, List
from datetime import datetime, timedelta
from astrbot import logger
from astrbot.core.config.astrbot_config import AstrBotConfig


class BotManager:
    def __init__(self, bot_data: Dict[str, Dict[str, Any]], config: AstrBotConfig):
        """
        管理多个群组的人机识别记录、监控与禁言状态。
        :param bot_data: 群组数据字典，格式见下：
            {
                "group_id": {
                    "bot_records": {"bot_id": "YYYY-MM-DD HH:MM:SS"},
                    "monitoring": True/False,
                    "ban": True/False
                }
            }
        :param config: 配置对象，用于保存更改。
        """
        self.data = bot_data
        self.config = config

    def _get_group(self, group_id: str) -> Dict[str, Any] | None:
        """获取指定群组的数据，如果不存在则返回 None 而不是创建新条目。"""
        return self.data.get(group_id, None)

    def _get_or_create_group(self, group_id: str) -> Dict[str, Any]:
        """获取指定群组的数据，如果不存在则创建默认值。"""
        default = {"bot_records": {}, "monitoring": False, "ban": False}
        return self.data.setdefault(group_id, default)

    def add_bot_record(self, group_id: str, bot_id: str) -> bool:
        """添加 Bot 记录，若已存在则返回 False。"""
        group = self._get_or_create_group(group_id)
        if bot_id not in group["bot_records"]:
            group["bot_records"][bot_id] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.config["bot_data_list"] = [self.data]
            self.config.save_config()
            logger.info(f"添加人机记录：群组 {group_id}，Bot ID {bot_id}")
            return True
        return False

    def remove_bot_record(self, group_id: str, bot_id: str) -> bool:
        """移除 Bot 记录。"""
        group = self._get_or_create_group(group_id)
        if bot_id in group["bot_records"]:
            del group["bot_records"][bot_id]
            self.config["bot_data_list"] = [self.data]
            self.config.save_config()
            logger.info(f"删除人机记录：群组 {group_id}，Bot ID {bot_id}")
            return True
        return False

    def view_bot_records(self, group_id: str):
        """查看群组下的所有 Bot 记录。"""
        group = self._get_or_create_group(group_id)
        return group["bot_records"]

    def is_monitoring(self, group_id: str) -> bool:
        """检查群组是否启用监控，不自动创建新的群组条目。"""
        group = self._get_group(group_id)
        return group.get("monitoring", False) if group else False

    def toggle_monitoring(self, group_id: str, enable: bool) -> None:
        """切换监控状态，但只在群组已经存在的情况下进行操作。"""
        if group := self._get_group(group_id):
            group["monitoring"] = enable


    def is_banned(self, group_id: str) -> bool:
        """检查群组是否启用禁言。"""
        group = self._get_or_create_group(group_id)
        return group["ban"]

    def toggle_ban(self, group_id: str, enable: bool) -> None:
        """切换禁言状态。"""
        self._get_or_create_group(group_id)["ban"] = enable
        self.config["bot_data_list"] = [self.data]
        self.config.save_config()
        status = "启用" if enable else "禁用"
        logger.info(f"群组 {group_id} 的禁言功能已 {status}")

    def check_speak_frequency(self, group_id: str, bot_id: str, threshold: int) -> bool:
        """
        检查发言频率是否超过阈值（单位：秒），不自动创建新的群组条目。
        超过则返回 False，否则更新时间并返回 True。
        """
        group = self._get_group(group_id)
        if group and "bot_records" in group:
            bot_records = group["bot_records"]
            last_time_str = bot_records.get(bot_id, None)
            now = datetime.now()

            bot_records[bot_id] = now.strftime("%Y-%m-%d %H:%M:%S")
            if last_time_str:
                last_time = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
                return (now - last_time) < timedelta(seconds=threshold)
            return True  # 第一次发言总是允许
        else:
            logger.warning(f"尝试访问未定义群组 {group_id} 或其 bot_records。")
            return False

    def get_groups(self) -> List[str]:
        """获取所有管理的群组 ID 列表。"""
        return list(self.data.keys())

    def get_bot_ids(self, group_id: str) -> List[str]:
        """获取指定群组下的所有 Bot ID。"""
        group = self._get_or_create_group(group_id)
        return list(group["bot_records"].keys())
