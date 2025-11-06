import random
from datetime import datetime, time, timedelta
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
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
]


@register(
    "astrbot_plugin_furry_zan",
    "AstrBot 芝士雪豹",
    "自动赞我插件 - 支持每日自动点赞",
    "1.0.0",
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
        
        # 设置默认的自动点赞时间（不再从配置读取）
        self.auto_like_hour = 9
        self.auto_like_minute = 0
        self.auto_like_second = 0
        
        self.notify_groups: list[str] = config.get("notify_groups", [])
        
        # 直接从配置获取订阅用户，不再使用单独的存储文件
        self.subscribed_users: list[str] = config.get("subscribed_users", [])
        
        # 数据存储（仅用于点赞日期）
        data_dir = Path("data/plugins/astrbot_plugin_furry_zan")
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
        logger.info(f"👥 订阅用户: {len(self.subscribed_users)} 人")

    def _load_store_data(self) -> dict:
        """加载存储数据（仅点赞日期和时间设置）"""
        try:
            with self.store_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载自动点赞数据失败: {e}")
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
        except Exception as e:
            logger.error(f"保存自动点赞数据失败: {e}")

    def _save_subscribed_users(self):
        """保存订阅用户到配置文件"""
        try:
            self.config["subscribed_users"] = self.subscribed_users
            self.config.save_config()
            logger.debug("订阅用户已保存到配置")
        except Exception as e:
            logger.error(f"保存订阅用户到配置失败: {e}")

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
            now = datetime.now(self.timezone)  # 使用带时区的时间
            today = now.date().strftime("%Y-%m-%d")
            
            # 检查今天是否已经点赞过
            if self.zanwo_date == today:
                logger.info(f"⏭️ 今天已经点赞过，跳过执行")
                return
            
            if not self.subscribed_users:
                logger.warning("⏭️ 没有订阅用户，跳过执行")
                return
            
            logger.info(f"🎯 开始执行自动点赞，目标用户: {len(self.subscribed_users)} 人")
            
            platforms = self.context.platform_manager.get_insts()
            for platform in platforms:
                if hasattr(platform, 'get_client'):
                    client = platform.get_client()
                    if client:
                        await self._refresh_friend_list(client)
                        
                        friend_users = [
                            user_id for user_id in self.subscribed_users 
                            if user_id in self.friend_list
                        ]
                        
                        if friend_users:
                            # 先发送开始通知
                            start_message = f"🤖 开始执行自动点赞\n⏰ 时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')}\n👥 目标用户: {len(friend_users)} 人\n🔢 每人点赞: {self.likes_per_user} 次"
                            await self.send_group_notification(start_message)
                            
                            # 执行点赞
                            result = await self._like(client, friend_users)
                            
                            # 更新最后点赞日期
                            self.zanwo_date = today
                            self._save_store_data()
                            
                            # 发送完成通知
                            complete_message = f"✅ 自动点赞执行完成\n⏰ 时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')}\n👥 成功点赞: {len(friend_users)} 人\n🔢 每人点赞: {self.likes_per_user} 次\n⏳ 下次点赞: {self.get_next_like_time()}"
                            await self.send_group_notification(complete_message)
                            
                            logger.info(f"✅ 已更新最后点赞日期为: {self.zanwo_date}")
                        else:
                            logger.warning("⚠️ 没有找到订阅的好友用户")
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
        """刷新好友列表"""
        try:
            # 强制刷新，不检查缓存时间
            friends = await client.get_friend_list()
            self.friend_list = [str(friend['user_id']) for friend in friends]
            self.last_friend_check = datetime.now()
            logger.info(f"👥 好友列表已刷新，共 {len(self.friend_list)} 个好友")
            return True
        except Exception as e:
            logger.error(f"刷新好友列表失败: {e}")
            return False

    async def _is_friend(self, client, user_id: str) -> bool:
        """检查是否为好友"""
        # 每次都强制刷新好友列表，确保能识别新加的好友
        await self._refresh_friend_list(client)
        return user_id in self.friend_list

    async def _like(self, client, ids: list[str]) -> str:
        """点赞的核心逻辑"""
        replys = []
        for user_id in ids:
            total_likes = 0
            error_reply = ""
            
            try:
                user_info = await client.get_stranger_info(user_id=int(user_id))
                username = user_info.get("nickname", "未知用户")
            except Exception as e:
                username = "未知用户"
            
            remaining_likes = self.likes_per_user
            success_count = 0
            
            while remaining_likes > 0 and success_count < 2:
                try:
                    like_times = min(10, remaining_likes)
                    await client.send_like(user_id=int(user_id), times=like_times)
                    total_likes += like_times
                    remaining_likes -= like_times
                    success_count += 1
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    error_message = str(e)
                    if "已达" in error_message:
                        error_reply = random.choice(limit_responses)
                    elif "权限" in error_message:
                        error_reply = "点赞权限受限"
                    else:
                        error_reply = f"点赞失败: {error_message}"
                    break

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
        """给单个用户点赞"""
        total_likes = 0
        error_reply = ""
        
        remaining_likes = self.likes_per_user
        success_count = 0
        
        while remaining_likes > 0 and success_count < 2:
            try:
                like_times = min(10, remaining_likes)
                await client.send_like(user_id=int(user_id), times=like_times)
                total_likes += like_times
                remaining_likes -= like_times
                success_count += 1
                await asyncio.sleep(1)
                
            except Exception as e:
                error_message = str(e)
                if "已达" in error_message:
                    error_reply = random.choice(limit_responses)
                elif "权限" in error_message:
                    error_reply = "点赞权限受限"
                else:
                    error_reply = f"点赞失败: {error_message}"
                break

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
        if self.enable_white_list_groups:
            if event.get_group_id() not in self.white_list_groups:
                return
        
        sender_id = event.get_sender_id()
        client = event.bot
        
        try:
            user_info = await client.get_stranger_info(user_id=int(sender_id))
            username = user_info.get("nickname", "未知用户")
        except:
            username = "未知用户"
        
        result = await self._like_single_user(client, sender_id, username)
        
        response = f"🎯 赞我功能\n👤 用户: {username}\n{result}"
        yield event.plain_result(response)

    @filter.command("订阅点赞")
    async def subscribe_like(self, event: AiocqhttpMessageEvent):
        """订阅点赞 - 强制刷新好友列表后检查"""
        sender_id = event.get_sender_id()
        
        client = event.bot
        
        if not await self._is_friend(client, sender_id):
            yield event.plain_result("❌ 订阅失败\n💡 请先加我为好友再订阅自动点赞哦~")
            return
            
        if sender_id in self.subscribed_users:
            yield event.plain_result("ℹ️ 订阅状态\n💡 你已经订阅点赞了哦~")
            return
        
        self.subscribed_users.append(sender_id)
        self._save_subscribed_users()  # 保存到配置文件
        
        logger.info(f"用户 {sender_id} 订阅了自动点赞")
        
        auto_time = f"{self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}"
        next_time = self.get_next_like_time()
        
        response = f"✅ 订阅成功\n⏰ 自动点赞时间: {auto_time}\n⏳ 下次点赞: {next_time}\n🔢 每人点赞: {self.likes_per_user} 次\n💡 提示: 只有好友才能订阅自动点赞"
        yield event.plain_result(response)

    @filter.command("取消订阅点赞")
    async def unsubscribe_like(self, event: AiocqhttpMessageEvent):
        """取消订阅点赞"""
        sender_id = event.get_sender_id()
        if sender_id not in self.subscribed_users:
            yield event.plain_result("ℹ️ 订阅状态\n💡 你还没有订阅点赞哦~")
            return
        
        self.subscribed_users.remove(sender_id)
        self._save_subscribed_users()  # 保存到配置文件
        
        logger.info(f"用户 {sender_id} 取消了自动点赞订阅")
        yield event.plain_result("✅ 取消订阅成功\n💡 我将不再自动给你点赞")

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
                yield event.plain_result("❌ 没有订阅用户")
                return
                
            yield event.plain_result("🔄 开始立即执行点赞...")
            
            platforms = self.context.platform_manager.get_insts()
            for platform in platforms:
                if hasattr(platform, 'get_client'):
                    client = platform.get_client()
                    if client:
                        # 强制刷新好友列表
                        await self._refresh_friend_list(client)
                        
                        friend_users = [
                            user_id for user_id in self.subscribed_users 
                            if user_id in self.friend_list
                        ]
                        
                        if friend_users:
                            result = await self._like(client, friend_users)
                            # 更新为今天的日期，避免重复点赞
                            self.zanwo_date = today
                            self._save_store_data()
                            
                            yield event.plain_result(f"✅ 立即点赞完成\n👥 成功点赞: {len(friend_users)} 人\n{result}")
                        else:
                            yield event.plain_result("❌ 没有找到订阅的好友用户")
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
        
        debug_info = f"🔍 调试信息\n当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}\n设置时间: {self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}\n最后点赞日期: {self.zanwo_date}\n今天日期: {today_date}\n日期不同: {self.zanwo_date != today_date}\n自动点赞启用: {self.auto_like_enabled}\n订阅用户数: {len(self.subscribed_users)}\n好友数: {len(self.friend_list)}\n通知群组: {len(self.notify_groups)}\n定时任务: {job_status}"
        
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
        
        status_info = f"🤖 点赞插件状态\n⏰ 自动点赞时间: {auto_time}\n⏳ 下次点赞: {next_time}\n📅 最后点赞日期: {self.zanwo_date}\n🔢 每人点赞: {self.likes_per_user} 次\n✅ 自动点赞: {'已开启' if self.auto_like_enabled else '已关闭'}\n👥 订阅用户: {len(self.subscribed_users)} 人\n📢 通知群组: {len(self.notify_groups)} 个\n🔄 定时任务: {job_status}"
        
        yield event.plain_result(status_info)

    async def terminate(self):
        """插件卸载时清理资源"""
        if self.auto_like_job:
            self.auto_like_job.remove()
        self.scheduler.shutdown()
        logger.info("🛑 自动点赞插件已停止") 