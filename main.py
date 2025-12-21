import random
from datetime import datetime, time, timedelta
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
import astrbot.api.message_components as Comp
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.permission import PermissionType
import asyncio
import json
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.job import Job
from apscheduler.triggers.cron import CronTrigger
import zoneinfo

# 点赞成功回复
success_responses = [
    "👍{total_likes}",
    "赞了赞了",
    "点赞成功！",
    "给{username}点了{total_likes}个赞",
    "赞送出去啦！一共{total_likes}个哦！",
    "为{username}点赞成功！总共{total_likes}个！",
    "点了{total_likes}个，快查收吧！",
    "赞已送达，请注意查收~ 一共{total_likes}个！",
    "给{username}点了{total_likes}个赞，记得回赞哟！",
    "赞了{total_likes}次，看看收到没？",
    "点了{total_likes}赞，没收到可能是我被风控了",
    "✨ {total_likes}个赞已到账，请查收~",
    "叮咚！{total_likes}个赞已送达{username}",
    "赞力全开！给{username}送了{total_likes}个赞",
    "biu~ {total_likes}个赞发射成功！",
    "{username}的赞+{total_likes}，声望提升！",
    "赞赞赞！一口气点了{total_likes}个",
    "今日份的{total_likes}个赞已安排~",
    "赞不完，根本赞不完！又点了{total_likes}个",
    "赞气满满！{total_likes}个赞请收好",
    "赞力觉醒！给{username}狂点{total_likes}个赞",
    "赞到成功！{total_likes}个赞已送达",
    "赞不绝口！又给{username}点了{total_likes}个",
    "赞力爆棚！今日{total_likes}个赞已送出",
]

# 点赞数到达上限回复
limit_responses = [
    "今天给{username}的赞已达上限",
    "赞了那么多还不够吗？",
    "{username}别太贪心哟~",
    "今天赞过啦！",
    "今天已经赞过啦~",
    "已经赞过啦~",
    "还想要赞？不给了！",
    "已经赞过啦，别再点啦！",
    "今日赞力已耗尽，明天再来吧~",
    "{username}今天已经收获满满啦！",
    "赞力不足，请明日再战！",
    "今日点赞任务已完成✓",
    "赞力恢复中，请稍后再试",
    "今日份的赞已经给{username}啦",
    "赞力有限，明天继续哦~",
    "{username}今天已经被赞爆啦！",
    "赞力CD中，请耐心等待",
    "今日点赞额度已用完",
    "赞力值归零，需要重新充能",
    "{username}今天太受欢迎啦！",
    "赞力过载，系统保护启动",
    "今日点赞成就已达成！",
]

# 已经自动回复
already_subscribed_responses = [
    "你已经自动点赞了哦~",
    "别急嘛，已经给你自动了~",
    "自动状态正常，坐等收赞吧！",
    "已经安排上啦，等着收赞吧~",
    "自动成功，就等时间到啦！",
    "别重复自动啦，已经在名单里了~",
    "已经在自动名单中啦！",
    "自动状态：已开启 ✓",
    "早就给你安排上自动点赞啦~",
    "自动点赞服务运行中...",
    "已经在自动名单里躺平啦~",
    "自动状态良好，无需重复操作",
    "早就把你加入自动名单啦！",
    "自动点赞已激活，无需重复",
    "已经在自动队列中啦~",
    "自动服务正常运行中",
    "早就给你设置好啦！",
    "自动状态：在线等赞",
    "已经在自动名单里啦~",
    "自动点赞已就绪，等待执行",
    "早就安排上自动点赞啦！",
    "自动状态：待机中",
]

# 自动成功回复
subscribe_success_responses = [
    "听到了！每天{time}准时给你点赞{count}次~",
    "安排上了！{time}开始点赞{count}次",
    "搞定！{time}自动点赞{count}次",
    "已经记住了，{time}执行{count}次",
    "自动设置完成！{time}给你点{count}个赞",
    "自动成功！坐等{time}收{count}个赞吧",
    "自动点赞已开启！{time}执行{count}次",
    "设置成功！每天{time}给你送{count}个赞",
    "自动点赞安排妥当！{time}开始{count}次",
    "已加入日程！{time}自动点赞{count}次",
    "提醒设置成功！{time}点赞{count}次",
    "自动点赞激活！{time}执行{count}次",
    "成功加入自动名单！{time}点赞{count}次",
    "自动点赞已部署！{time}开始{count}次",
    "设置完成！{time}自动送{count}个赞",
    "自动点赞礼包已激活！{time}发放{count}次",
    "未来已安排！{time}点赞{count}次",
    "自动服务开启！{time}执行{count}次",
    "魔法生效！{time}自动点赞{count}次",
    "自动点赞马戏团开演！{time}表演{count}次",
    "自动点赞冠军已诞生！{time}执行{count}次",
    "摇滚起来！{time}自动点赞{count}次",
]

# 取消自动回复
unsubscribe_responses = [
    "✅ 取消自动成功",
    "已取消自动，不再给你点赞啦",
    "取消成功，以后不给你点赞了",
    "已经删除了你的信息哦",
    "自动已取消，需要时再叫我~",
    "自动点赞已关闭",
    "取消成功，不再自动点赞",
    "自动服务已终止",
    "已退出自动点赞计划",
    "自动锁定已解除",
    "自动点赞气球已放飞",
    "自动服务日落西山",
    "自动点赞已停止",
    "自动服务进入休眠",
    "自动点赞已关机",
    "已取消自动点赞目标",
    "自动点赞锚已收起",
    "自动点赞浪潮已退去",
    "自动点赞马戏团已散场",
    "自动服务到此结束",
    "自动点赞竞赛已完结",
    "自动点赞魔法已解除",
]

# 自动失败回复（非好友）
not_friend_responses = [
    "自动失败，请先加我为好友哦~",
    "要先成为好友才能自动点赞呢",
    "加个好友先吧，不然没法自动",
    "咱们先加个好友呗~",
    "成为好友才能开启自动服务",
    "目标锁定失败，请先加好友",
    "好友之门尚未开启",
    "成为好友，点赞更轻松",
    "友情提示：请先加为好友",
    "成为好友解锁自动点赞",
    "好友关系是自动点赞的前提",
    "加个好友，点赞更精彩",
    "成为好友，开启点赞之旅",
    "好友认证是自动点赞的钥匙",
    "魔法提示：请先建立好友关系",
    "摇滚起来！先加个好友吧",
    "成为好友，争夺点赞冠军",
    "马戏团规则：先加好友再表演",
    "友情建议：加个好友更方便",
    "成为好友，点亮自动点赞",
    "游戏规则：好友才能自动",
    "系统提示：请先添加好友",
]

# 在黑名单中的回复消息
blacklist_responses = [
    "❌ 你在黑名单中，无法使用点赞功能",
    "🚫 黑名单用户禁止使用本插件",
    "⛔ 抱歉，你在黑名单中，无法点赞",
    "🔒 黑名单限制，请联系管理员",
    "🚷 禁止访问：你在黑名单中",
    "⚡ 权限被拒绝：你在黑名单中",
    "🛑 操作被阻止：你在黑名单中",
    "⏸️ 暂停服务：你在黑名单中",
    "🔐 访问受限：黑名单用户",
    "🚨 安全警告：黑名单用户禁止操作",
    "🎭 不好意思，你在黑名单中哦",
    "💢 黑名单用户还想点赞？想得美！",
    "😤 黑名单用户禁止使用此功能",
    "🚯 黑名单用户请勿操作",
    "📵 权限不足：黑名单用户",
    "🔞 年龄不够？不，是黑名单！",
    "🧱 你被墙了，黑名单用户",
    "⚖️ 公正裁决：黑名单用户禁止",
    "🧯 紧急阻止：黑名单用户操作",
    "🪤 触发陷阱：黑名单用户",
    "🔨 黑名单用户被锤了",
    "🗑️ 黑名单用户请左转离开"
]


@register(
    "astrbot_plugin_furry_zan",
    "AstrBot 芝士雪豹",
    "自动赞我插件 - 支持每日自动点赞",
    "1.3.0",
    "https://github.com/furry520-source/astrbot_plugin_furry_zan",
)
class AutoZanWo(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.success_responses = success_responses
        
        # 从配置获取设置
        self.enable_white_list_groups: bool = config.get("enable_white_list_groups", False)
        self.white_list_groups: list[str] = config.get("white_list_groups", [])
        self.auto_like_enabled: bool = config.get("auto_like_enabled", True)
        self.likes_per_user: int = config.get("likes_per_user", 20)
        
        # 新增：黑名单用户
        self.blacklist_users: list[str] = config.get("blacklist_users", [])
        
        # 设置默认的自动点赞时间（不再从配置读取）
        self.auto_like_hour = 9
        self.auto_like_minute = 0
        self.auto_like_second = 0
        
        self.notify_groups: list[str] = config.get("notify_groups", [])
        
        # 直接从配置获取自动用户，不再使用单独的存储文件
        self.subscribed_users: list[str] = config.get("subscribed_users", [])
        
        # 数据存储（仅用于点赞日期）- 使用 StarTools 获取数据目录
        data_dir = StarTools.get_data_dir("astrbot_plugin_furry_zan")
        self.store_path = data_dir / "auto_like_data.json"
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self.store_path.write_text("{}", encoding="utf-8")
        
        # 加载存储数据（仅点赞日期和时间设置）
        store_data = self._load_store_data()
        self.zanwo_date: str = store_data.get("zanwo_date", "2025-01-01")
        
        # 存储自动点赞时间设置
        self.schedule_data = store_data.get("schedule", {})
        if self.schedule_data:
            self.auto_like_hour = self.schedule_data.get("hour", 9)
            self.auto_like_minute = self.schedule_data.get("minute", 0)
            self.auto_like_second = self.schedule_data.get("second", 0)
        
        # 缓存好友列表
        self.friend_list: list[str] = []
        self.last_friend_check: datetime = None
        
        # 定时任务调度器
        tz = self.context.get_config().get("timezone")
        self.timezone = zoneinfo.ZoneInfo(tz) if tz else zoneinfo.ZoneInfo("Asia/Shanghai")
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self.scheduler.start()
        
        self.auto_like_job: Job | None = None
        
        # 启动定时任务
        self._setup_auto_like_job()
        
        logger.info(f"🤖 自动点赞插件初始化完成")
        logger.info(f"⏰ 自动点赞时间: {self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}")
        logger.info(f"📅 最后点赞日期: {self.zanwo_date}")
        logger.info(f"👥 自动用户: {len(self.subscribed_users)} 人")
        logger.info(f"🚫 黑名单用户: {len(self.blacklist_users)} 人")

    def _is_blacklisted(self, user_id: str) -> bool:
        """检查用户是否在黑名单中"""
        return user_id in self.blacklist_users

    def _load_store_data(self) -> dict:
        """加载存储数据（仅点赞日期和时间设置）"""
        try:
            with self.store_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"数据文件 {self.store_path} 不存在，将使用默认值。")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"解析自动点赞数据失败，文件可能已损坏: {e}")
            return {}
        except Exception as e:
            logger.error(f"加载自动点赞数据时发生未知错误: {e}")
            return {}

    def _save_store_data(self):
        """保存存储数据（仅点赞日期和时间设置）"""
        try:
            data = {
                "zanwo_date": self.zanwo_date,
                "schedule": {
                    "hour": self.auto_like_hour,
                    "minute": self.auto_like_minute,
                    "second": self.auto_like_second
                }
            }
            with self.store_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug("自动点赞数据已保存")
        except IOError as e:
            logger.error(f"保存自动点赞数据失败（IO错误）: {e}")
        except Exception as e:
            logger.error(f"保存自动点赞数据时发生未知错误: {e}")

    def _save_subscribed_users(self):
        """保存自动用户到配置文件"""
        try:
            self.config["subscribed_users"] = self.subscribed_users
            self.config.save_config()
            logger.debug("自动用户已保存到配置")
        except Exception as e:
            logger.error(f"保存自动用户到配置失败: {e}")

    def _setup_auto_like_job(self):
        """设置自动点赞定时任务"""
        if self.auto_like_job:
            self.auto_like_job.remove()
            self.auto_like_job = None
        
        if self.auto_like_enabled:
            try:
                self.auto_like_job = self.scheduler.add_job(
                    self._execute_auto_like,
                    trigger=CronTrigger(
                        hour=self.auto_like_hour,
                        minute=self.auto_like_minute,
                        second=self.auto_like_second
                    ),
                    name="auto_like_daily",
                    misfire_grace_time=300,  # 5分钟内错过仍执行
                )
                logger.info(f"✅ 自动点赞定时任务已设置: {self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}")
                
                # 立即检查是否需要执行（如果当前时间在设定时间之后）
                now = datetime.now(self.timezone)
                today_target = datetime(
                    now.year, now.month, now.day, 
                    self.auto_like_hour, self.auto_like_minute, self.auto_like_second,
                    tzinfo=self.timezone
                )
                
                if now >= today_target and self.zanwo_date != now.date().strftime("%Y-%m-%d"):
                    logger.info("🕒 当前时间已过设定时间且未点赞，立即执行")
                    asyncio.create_task(self._execute_auto_like())
                    
            except Exception as e:
                logger.error(f"设置定时任务失败: {e}")
        else:
            logger.info("❌ 自动点赞功能已禁用")

    async def _execute_auto_like(self):
        """执行自动点赞"""
        try:
            now = datetime.now(self.timezone)
            today = now.date().strftime("%Y-%m-%d")
            
            # 检查今天是否已经点赞过
            if self.zanwo_date == today:
                logger.info(f"⏭️ 今天已经点赞过，跳过执行")
                return
            
            if not self.subscribed_users:
                logger.warning("⏭️ 没有自动用户，跳过执行")
                return
            
            logger.info(f"🎯 开始执行自动点赞，目标用户: {len(self.subscribed_users)} 人")
            
            platforms = self.context.platform_manager.get_insts()
            for platform in platforms:
                if hasattr(platform, 'get_client'):
                    client = platform.get_client()
                    if client:
                        await self._refresh_friend_list(client)
                        
                        # 过滤掉黑名单用户
                        valid_users = [
                            user_id for user_id in self.subscribed_users 
                            if user_id in self.friend_list and not self._is_blacklisted(user_id)
                        ]
                        
                        if valid_users:
                            # 先发送开始通知
                            start_message = f"🤖 开始执行自动点赞\n⏰ 时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')}\n👥 目标用户: {len(valid_users)} 人\n🔢 每人点赞: {self.likes_per_user} 次"
                            await self.send_group_notification(start_message)
                            
                            # 执行点赞
                            result = await self._like_multiple_users(client, valid_users)
                            
                            # 更新最后点赞日期
                            self.zanwo_date = today
                            self._save_store_data()
                            
                            # 发送完成通知
                            complete_message = f"✅ 自动点赞执行完成\n⏰ 时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')}\n👥 成功点赞: {len(valid_users)} 人\n🔢 每人点赞: {self.likes_per_user} 次\n⏳ 下次点赞: {self.get_next_like_time()}"
                            await self.send_group_notification(complete_message)
                            
                            logger.info(f"✅ 已更新最后点赞日期为: {self.zanwo_date}")
                        else:
                            logger.warning("⚠️ 没有找到自动的好友用户或所有用户都在黑名单中")
                            # 即使没有好友用户，也更新日期避免重复检查
                            self.zanwo_date = today
                            self._save_store_data()
                        break
        
        except Exception as e:
            logger.error(f"自动点赞执行失败: {e}", exc_info=True)
            error_message = f"❌ 自动点赞执行失败\n💡 错误: {str(e)}"
            await self.send_group_notification(error_message)

    def get_next_like_time(self) -> str:
        """获取下次点赞的详细时间"""
        now = datetime.now(self.timezone)
        today_target = datetime(
            now.year, now.month, now.day, 
            self.auto_like_hour, self.auto_like_minute, self.auto_like_second,
            tzinfo=self.timezone
        )
        
        if now < today_target:
            next_time = today_target
        else:
            next_time = today_target + timedelta(days=1)
        
        return next_time.strftime("%Y年%m月%d日 %H:%M:%S")

    async def send_group_notification(self, message: str):
        """发送群通知"""
        if not self.notify_groups:
            return
            
        try:
            platforms = self.context.platform_manager.get_insts()
            for platform in platforms:
                if hasattr(platform, 'get_client'):
                    client = platform.get_client()
                    if client:
                        for group_id in self.notify_groups:
                            try:
                                await client.send_group_msg(group_id=int(group_id), message=message)
                                logger.info(f"📢 已发送群通知到群 {group_id}")
                                await asyncio.sleep(1)
                            except Exception as e:
                                logger.error(f"发送群通知到群 {group_id} 失败: {e}")
                        break
        except Exception as e:
            logger.error(f"发送群通知失败: {e}")

    async def _refresh_friend_list(self, client) -> bool:
        """刷新好友列表 - 添加缓存机制"""
        try:
            # 检查缓存是否过期（5分钟）
            if (self.last_friend_check and 
                (datetime.now() - self.last_friend_check).total_seconds() < 300):
                return True
                
            friends = await client.get_friend_list()
            self.friend_list = [str(friend['user_id']) for friend in friends]
            self.last_friend_check = datetime.now()
            logger.info(f"👥 好友列表已刷新，共 {len(self.friend_list)} 个好友")
            return True
        except Exception as e:
            logger.error(f"刷新好友列表失败: {e}")
            return False

    async def _is_friend(self, client, user_id: str) -> bool:
        """检查是否为好友 - 使用缓存"""
        # 确保好友列表是最新的
        await self._refresh_friend_list(client)
        return user_id in self.friend_list

    async def _execute_like_for_user(self, client, user_id: str) -> tuple[int, str]:
        """执行单个用户的点赞逻辑 - 核心点赞函数"""
        total_likes = 0
        error_reply = ""
        
        remaining_likes = self.likes_per_user
        
        while remaining_likes > 0:
            try:
                like_times = min(10, remaining_likes)
                await client.send_like(user_id=int(user_id), times=like_times)
                total_likes += like_times
                remaining_likes -= like_times
                await asyncio.sleep(1)  # 每次调用后适当休眠
                
            except Exception as e:
                error_message = str(e)
                if "已达" in error_message:
                    error_reply = random.choice(limit_responses)
                elif "权限" in error_message:
                    error_reply = "点赞权限受限，你好像没开陌生人点赞"
                else:
                    error_reply = f"点赞失败: {error_message}"
                break

        return total_likes, error_reply

    async def _like_multiple_users(self, client, user_ids: list[str]) -> str:
        """给多个用户点赞"""
        replys = []
        for user_id in user_ids:
            try:
                user_info = await client.get_stranger_info(user_id=int(user_id))
                username = user_info.get("nickname", "未知用户")
            except Exception:
                username = "未知用户"
            
            total_likes, error_reply = await self._execute_like_for_user(client, user_id)
            
            if total_likes > 0:
                reply = random.choice(self.success_responses)
                if "{username}" in reply:
                    reply = reply.replace("{username}", username)
                if "{total_likes}" in reply:
                    reply = reply.replace("{total_likes}", str(total_likes))
                replys.append(reply)
            elif error_reply:
                if "{username}" in error_reply:
                    error_reply = error_reply.replace("{username}", username)
                replys.append(error_reply)

        return "\n".join(replys).strip()

    async def _like_single_user(self, client, user_id: str, username: str = "未知用户") -> str:
        """给单个用户点赞 - 复用核心逻辑"""
        total_likes, error_reply = await self._execute_like_for_user(client, user_id)
        
        if total_likes > 0:
            reply = random.choice(self.success_responses)
            if "{username}" in reply:
                reply = reply.replace("{username}", username)
            if "{total_likes}" in reply:
                reply = reply.replace("{total_likes}", str(total_likes))
            return reply
        elif error_reply:
            if "{username}" in error_reply:
                error_reply = error_reply.replace("{username}", username)
            return error_reply
        
        return "点赞失败"

    @filter.regex(r"^赞我$")
    async def like_me_public(self, event: AiocqhttpMessageEvent):
        """赞我功能 - 任何人都可以使用，不需要加好友"""
        # 检查黑名单
        sender_id = event.get_sender_id()
        if self._is_blacklisted(sender_id):
            reply = random.choice(blacklist_responses)
            yield event.plain_result(reply)
            return
        
        # 简化条件判断
        if self.enable_white_list_groups and event.get_group_id() not in self.white_list_groups:
            return
        
        client = event.bot
        
        try:
            user_info = await client.get_stranger_info(user_id=int(sender_id))
            username = user_info.get("nickname", "未知用户")
        except Exception:
            username = "未知用户"
        
        result = await self._like_single_user(client, sender_id, username)
        
        # 简化回复，只保留点赞结果
        yield event.plain_result(result)

    @filter.command("自动点赞")
    async def subscribe_like(self, event: AiocqhttpMessageEvent):
        """自动点赞 - 使用缓存的好友列表"""
        sender_id = event.get_sender_id()
        
        # 检查黑名单
        if self._is_blacklisted(sender_id):
            reply = random.choice(blacklist_responses)
            yield event.plain_result(reply)
            return
        
        client = event.bot
        
        if not await self._is_friend(client, sender_id):
            reply = random.choice(not_friend_responses)
            yield event.plain_result(reply)
            return
            
        if sender_id in self.subscribed_users:
            reply = random.choice(already_subscribed_responses)
            yield event.plain_result(reply)
            return
        
        self.subscribed_users.append(sender_id)
        self._save_subscribed_users()
        
        logger.info(f"用户 {sender_id} 自动了自动点赞")
        
        auto_time = f"{self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}"
        next_time = self.get_next_like_time()
        
        # 使用随机回复
        reply_template = random.choice(subscribe_success_responses)
        reply = reply_template.format(
            time=auto_time,
            count=self.likes_per_user
        )
        
        yield event.plain_result(reply)

    @filter.command("取消自动点赞")
    async def unsubscribe_like(self, event: AiocqhttpMessageEvent):
        """取消自动点赞"""
        sender_id = event.get_sender_id()
        
        # 黑名单用户也可以取消自动
        if sender_id not in self.subscribed_users:
            reply = random.choice(already_subscribed_responses).replace("已经", "还没有").replace("别重复", "还没有")
            yield event.plain_result(reply)
            return
        
        self.subscribed_users.remove(sender_id)
        self._save_subscribed_users()
        
        logger.info(f"用户 {sender_id} 取消了自动点赞自动")
        
        reply = random.choice(unsubscribe_responses)
        yield event.plain_result(reply)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("添加黑名单")
    async def add_blacklist(self, event: AiocqhttpMessageEvent, user_id: str):
        """添加用户到黑名单"""
        try:
            if not user_id.isdigit():
                yield event.plain_result("❌ 格式错误\n💡 请输入正确的QQ号")
                return
                
            if user_id in self.blacklist_users:
                yield event.plain_result(f"❌ 用户 {user_id} 已在黑名单中")
                return
            
            self.blacklist_users.append(user_id)
            self.config["blacklist_users"] = self.blacklist_users
            self.config.save_config()
            
            # 如果用户在自动列表中，自动取消自动
            if user_id in self.subscribed_users:
                self.subscribed_users.remove(user_id)
                self._save_subscribed_users()
                logger.info(f"用户 {user_id} 被加入黑名单，已自动取消自动")
                yield event.plain_result(f"✅ 已添加用户 {user_id} 到黑名单\n⚠️ 已自动取消该用户的自动")
            else:
                yield event.plain_result(f"✅ 已添加用户 {user_id} 到黑名单")
                
            logger.info(f"管理员添加用户 {user_id} 到黑名单")
            
        except Exception as e:
            logger.error(f"添加黑名单失败: {e}")
            yield event.plain_result(f"❌ 添加黑名单失败\n💡 错误: {e}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("移除黑名单")
    async def remove_blacklist(self, event: AiocqhttpMessageEvent, user_id: str):
        """从黑名单移除用户"""
        try:
            if not user_id.isdigit():
                yield event.plain_result("❌ 格式错误\n💡 请输入正确的QQ号")
                return
                
            if user_id not in self.blacklist_users:
                yield event.plain_result(f"❌ 用户 {user_id} 不在黑名单中")
                return
            
            self.blacklist_users.remove(user_id)
            self.config["blacklist_users"] = self.blacklist_users
            self.config.save_config()
            
            yield event.plain_result(f"✅ 已从黑名单移除用户 {user_id}")
            
            logger.info(f"管理员从黑名单移除用户 {user_id}")
            
        except Exception as e:
            logger.error(f"移除黑名单失败: {e}")
            yield event.plain_result(f"❌ 移除黑名单失败\n💡 错误: {e}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("查看黑名单")
    async def view_blacklist(self, event: AiocqhttpMessageEvent):
        """查看黑名单用户列表"""
        try:
            if not self.blacklist_users:
                yield event.plain_result("📝 黑名单当前为空")
                return
                
            blacklist_str = "\n".join([f"• {user_id}" for user_id in self.blacklist_users])
            response = f"📋 黑名单用户列表（共 {len(self.blacklist_users)} 人）：\n{blacklist_str}"
            yield event.plain_result(response)
            
        except Exception as e:
            logger.error(f"查看黑名单失败: {e}")
            yield event.plain_result(f"❌ 查看黑名单失败\n💡 错误: {e}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("设置点赞时间")
    async def set_auto_like_time(self, event: AiocqhttpMessageEvent, time_str: str):
        """设置自动点赞时间 - 支持 HH:MM:SS 格式，自动重置点赞日期"""
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                hour = int(parts[0])
                minute = int(parts[1])
                second = int(parts[2])
            elif len(parts) == 2:
                hour = int(parts[0])
                minute = int(parts[1])
                second = 0
            else:
                hour = int(time_str)
                minute = 0
                second = 0
            
            if not (0 <= hour <= 23):
                yield event.plain_result("❌ 设置失败\n💡 小时必须在 0-23 之间")
                return
            if not (0 <= minute <= 59):
                yield event.plain_result("❌ 设置失败\n💡 分钟必须在 0-59 之间")
                return
            if not (0 <= second <= 59):
                yield event.plain_result("❌ 设置失败\n💡 秒数必须在 0-59 之间")
                return
                
            # 保存旧时间用于比较
            old_time_str = f"{self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}"
            
            # 更新为新时间
            self.auto_like_hour = hour
            self.auto_like_minute = minute
            self.auto_like_second = second
            
            # 自动重置点赞日期，确保新时间设置后可以立即生效
            now = datetime.now(self.timezone)
            today = now.date().strftime("%Y-%m-%d")
            old_date = self.zanwo_date
            
            if self.zanwo_date == today:
                # 如果今天已经点赞过，重置为昨天，确保新时间设置后可以立即生效
                yesterday = (now - timedelta(days=1)).date().strftime("%Y-%m-%d")
                self.zanwo_date = yesterday
                date_reset_msg = f"\n📅 点赞日期已重置: {old_date} → {yesterday}"
                logger.info(f"设置时间时自动重置点赞日期: {old_date} -> {yesterday}")
            else:
                date_reset_msg = f"\n📅 点赞日期保持不变: {self.zanwo_date}"
            
            # 保存到存储文件
            self._save_store_data()
            
            # 重新设置定时任务
            self._setup_auto_like_job()
            
            logger.info(f"设置自动点赞时间: {old_time_str} -> {time_str}")
            
            next_time = self.get_next_like_time()
            
            response = f"✅ 时间设置成功\n⏰ 自动点赞时间: {old_time_str} → {time_str}{date_reset_msg}\n⏳ 下次点赞: {next_time}"
            yield event.plain_result(response)
            
        except ValueError:
            yield event.plain_result("❌ 设置失败\n💡 时间格式错误，请使用 HH:MM:SS 格式\n💡 例如: 15:30:00 或 15:30 或 15")
        except Exception as e:
            logger.error(f"设置点赞时间失败: {e}")
            yield event.plain_result(f"❌ 设置失败\n💡 错误: {e}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("立即点赞")
    async def immediate_like(self, event: AiocqhttpMessageEvent):
        """立即执行点赞（测试用）- 自动处理日期检查"""
        try:
            now = datetime.now(self.timezone)
            today = now.date().strftime("%Y-%m-%d")
            
            # 检查今天是否已经点赞过，如果点赞过则重置日期
            if self.zanwo_date == today:
                old_date = self.zanwo_date
                # 重置为昨天的日期，这样今天就可以重新点赞了
                yesterday = (now - timedelta(days=1)).date().strftime("%Y-%m-%d")
                self.zanwo_date = yesterday
                logger.info(f"检测到今天已点赞，自动重置日期: {old_date} -> {yesterday}")
                yield event.plain_result(f"🔄 检测到今天已点赞过，自动重置日期后继续执行...")
                
            if not self.subscribed_users:
                yield event.plain_result("❌ 没有自动用户")
                return
                
            yield event.plain_result("🔄 开始立即执行点赞...")
            
            platforms = self.context.platform_manager.get_insts()
            for platform in platforms:
                if hasattr(platform, 'get_client'):
                    client = platform.get_client()
                    if client:
                        # 刷新好友列表
                        await self._refresh_friend_list(client)
                        
                        # 过滤掉黑名单用户
                        friend_users = [
                            user_id for user_id in self.subscribed_users 
                            if user_id in self.friend_list and not self._is_blacklisted(user_id)
                        ]
                        
                        if friend_users:
                            result = await self._like_multiple_users(client, friend_users)
                            # 更新为今天的日期，避免重复点赞
                            self.zanwo_date = today
                            self._save_store_data()
                            
                            yield event.plain_result(f"✅ 立即点赞完成\n👥 成功点赞: {len(friend_users)} 人\n{result}")
                        else:
                            yield event.plain_result("❌ 没有找到自动的好友用户或所有用户都在黑名单中")
                        break
            else:
                yield event.plain_result("❌ 未找到可用的客户端")
                
        except Exception as e:
            logger.error(f"立即点赞失败: {e}")
            yield event.plain_result(f"❌ 立即点赞失败: {e}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("调试信息")
    async def debug_info(self, event: AiocqhttpMessageEvent):
        """查看详细的调试信息"""
        now = datetime.now(self.timezone)
        today_date = now.date().strftime("%Y-%m-%d")
        
        # 检查定时任务状态
        job_status = "未设置"
        if self.auto_like_job:
            next_run = self.auto_like_job.next_run_time
            job_status = f"已设置，下次运行: {next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else '无'}"
        
        debug_info = f"🔍 调试信息\n当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}\n设置时间: {self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}\n最后点赞日期: {self.zanwo_date}\n今天日期: {today_date}\n日期不同: {self.zanwo_date != today_date}\n自动点赞启用: {self.auto_like_enabled}\n自动用户数: {len(self.subscribed_users)}\n黑名单用户数: {len(self.blacklist_users)}\n好友数: {len(self.friend_list)}\n通知群组: {len(self.notify_groups)}\n定时任务: {job_status}"
        
        should_auto_like = (
            self.auto_like_enabled and 
            len(self.subscribed_users) > 0 and 
            self.zanwo_date != today_date
        )
        
        debug_info += f"\n满足自动点赞条件: {should_auto_like}\n下次点赞: {self.get_next_like_time()}"
        
        yield event.plain_result(debug_info)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("点赞状态")
    async def like_status(self, event: AiocqhttpMessageEvent):
        """查看点赞插件状态"""
        auto_time = f"{self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}"
        next_time = self.get_next_like_time()
        
        # 检查定时任务状态
        job_status = "✅ 运行中" if self.auto_like_job else "❌ 未运行"
        
        status_info = f"🤖 点赞插件状态\n⏰ 自动点赞时间: {auto_time}\n⏳ 下次点赞: {next_time}\n📅 最后点赞日期: {self.zanwo_date}\n🔢 每人点赞: {self.likes_per_user} 次\n✅ 自动点赞: {'已开启' if self.auto_like_enabled else '已关闭'}\n👥 自动用户: {len(self.subscribed_users)} 人\n🚫 黑名单用户: {len(self.blacklist_users)} 人\n📢 通知群组: {len(self.notify_groups)} 个\n🔄 定时任务: {job_status}"
        
        yield event.plain_result(status_info)

    async def terminate(self):
        """插件卸载时清理资源"""
        if self.auto_like_job:
            self.auto_like_job.remove()
        self.scheduler.shutdown()
        logger.info("🛑 自动点赞插件已停止")