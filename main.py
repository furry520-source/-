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
    "https://github.com/your-repo/astrbot_plugin_auto_zanwo",
)
class AutoZanWo(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.success_responses = success_responses
        
        # 从配置获取设置
        self.enable_white_list_groups: bool = config.get("enable_white_list_groups", False)
        self.white_list_groups: list[str] = config.get("white_list_groups", [])
        self.subscribed_users: list[str] = config.get("subscribed_users", [])
        self.zanwo_date: str = config.get("zanwo_date", "2025-01-01")
        self.auto_like_enabled: bool = config.get("auto_like_enabled", True)
        self.likes_per_user: int = config.get("likes_per_user", 20)
        
        # 解析时间字符串
        auto_like_time_str = config.get("auto_like_time", "09:00:00")
        time_parts = auto_like_time_str.split(':')
        if len(time_parts) >= 3:
            self.auto_like_hour = int(time_parts[0])
            self.auto_like_minute = int(time_parts[1])
            self.auto_like_second = int(time_parts[2])
        elif len(time_parts) == 2:
            self.auto_like_hour = int(time_parts[0])
            self.auto_like_minute = int(time_parts[1])
            self.auto_like_second = 0
        else:
            self.auto_like_hour = 9
            self.auto_like_minute = 0
            self.auto_like_second = 0
        
        self.notify_groups: list[str] = config.get("notify_groups", [])
        self.notify_delay: int = config.get("notify_delay", 1)  # 通知延迟配置化
        
        # 缓存好友列表
        self.friend_list: list[str] = []
        self.last_friend_check: datetime = None
        
        # 后台任务管理
        self._auto_like_task: asyncio.Task = None
        
        # 记录配置变更前的旧时间，用于检测时间修改
        self._old_auto_like_time = (self.auto_like_hour, self.auto_like_minute, self.auto_like_second)
        
        logger.info(f"🤖 自动点赞插件初始化完成")
        logger.info(f"⏰ 自动点赞时间: {self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}")
        logger.info(f"📅 最后点赞日期: {self.zanwo_date}")
        logger.info(f"👥 订阅用户: {len(self.subscribed_users)} 人")

    async def on_astrbot_loaded(self):
        """AstrBot加载完成后启动自动点赞任务"""
        self._auto_like_task = asyncio.create_task(self._auto_like_checker())
        logger.info("🚀 自动点赞任务已启动")

    async def terminate(self):
        """插件卸载时清理资源"""
        if self._auto_like_task:
            self._auto_like_task.cancel()
            try:
                await self._auto_like_task
            except asyncio.CancelledError:
                pass
            logger.info("🛑 自动点赞任务已停止")

    def get_next_like_time(self) -> str:
        """获取下次点赞的详细时间"""
        now = datetime.now()
        today_target = datetime(now.year, now.month, now.day, self.auto_like_hour, self.auto_like_minute, self.auto_like_second)
        
        if now < today_target:
            next_time = today_target
        else:
            next_time = today_target + timedelta(days=1)
        
        return next_time.strftime("%Y年%m月%d日 %H:%M:%S")

    async def check_and_fix_date_issue(self, check_time_change: bool = False) -> str:
        """检查并自动修复日期问题"""
        now = datetime.now()
        today = now.date().strftime("%Y-%m-%d")
        
        # 使用time对象简化时间比较
        target_time = time(self.auto_like_hour, self.auto_like_minute, self.auto_like_second)
        current_time = now.time()
        
        # 检查时间是否被修改过
        time_changed = False
        if check_time_change:
            old_hour, old_minute, old_second = self._old_auto_like_time
            time_changed = (old_hour != self.auto_like_hour or 
                          old_minute != self.auto_like_minute or 
                          old_second != self.auto_like_second)
        
        # 如果最后点赞日期是今天，但当前时间已经过了设置的点赞时间，说明今天应该点赞但被阻止了
        # 或者时间被修改过，需要重新评估
        should_fix = (
            self.auto_like_enabled and 
            len(self.subscribed_users) > 0 and 
            self.zanwo_date == today and
            (
                # 情况1：当前时间已经超过了设置的点赞时间
                current_time > target_time or
                # 情况2：时间被修改过，且新时间在当前时间之前
                (time_changed and target_time < current_time)
            )
        )
        
        if should_fix:
            yesterday = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
            old_date = self.zanwo_date
            self.zanwo_date = yesterday
            self.config["zanwo_date"] = self.zanwo_date
            self.config.save_config()
            
            # 更新旧时间记录
            self._old_auto_like_time = (self.auto_like_hour, self.auto_like_minute, self.auto_like_second)
            
            reason = "时间已过" if current_time > target_time else "时间修改"
            logger.info(f"🔧 自动修复日期问题 ({reason}): {old_date} -> {yesterday}")
            
            if time_changed:
                return f"🔧 时间修改自动修复\n原日期: {old_date} → 新日期: {yesterday}\n💡 今天将按照新时间重新打卡"
            else:
                return f"🔧 已自动修复日期问题\n原日期: {old_date} → 新日期: {yesterday}"
        
        return ""

    async def update_config_from_file(self):
        """从配置文件重新加载配置，并检查时间变化"""
        # 保存旧时间用于比较
        old_time = (self.auto_like_hour, self.auto_like_minute, self.auto_like_second)
        
        # 重新加载配置
        self.enable_white_list_groups = self.config.get("enable_white_list_groups", False)
        self.white_list_groups = self.config.get("white_list_groups", [])
        self.subscribed_users = self.config.get("subscribed_users", [])
        self.zanwo_date = self.config.get("zanwo_date", "2025-01-01")
        self.auto_like_enabled = self.config.get("auto_like_enabled", True)
        self.likes_per_user = self.config.get("likes_per_user", 20)
        
        # 解析新的时间字符串
        auto_like_time_str = self.config.get("auto_like_time", "09:00:00")
        time_parts = auto_like_time_str.split(':')
        if len(time_parts) >= 3:
            self.auto_like_hour = int(time_parts[0])
            self.auto_like_minute = int(time_parts[1])
            self.auto_like_second = int(time_parts[2])
        elif len(time_parts) == 2:
            self.auto_like_hour = int(time_parts[0])
            self.auto_like_minute = int(time_parts[1])
            self.auto_like_second = 0
        else:
            self.auto_like_hour = int(auto_like_time_str)
            self.auto_like_minute = 0
            self.auto_like_second = 0
        
        self.notify_groups = self.config.get("notify_groups", [])
        self.notify_delay = self.config.get("notify_delay", 1)
        
        # 检查时间是否变化并自动修复日期问题
        new_time = (self.auto_like_hour, self.auto_like_minute, self.auto_like_second)
        if old_time != new_time:
            logger.info(f"⏰ 检测到时间配置变化: {old_time[0]:02d}:{old_time[1]:02d}:{old_time[2]:02d} -> {new_time[0]:02d}:{new_time[1]:02d}:{new_time[2]:02d}")
            self._old_auto_like_time = old_time
            fix_result = await self.check_and_fix_date_issue(check_time_change=True)
            if fix_result:
                logger.info(f"🔄 配置更新自动修复: {fix_result}")

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
                                # 使用配置化的延迟
                                await asyncio.sleep(self.notify_delay)
                            except Exception as e:
                                logger.error(f"发送群通知到群 {group_id} 失败: {e}")
                        break
        except Exception as e:
            logger.error(f"发送群通知失败: {e}")

    async def _refresh_friend_list(self, client) -> bool:
        """刷新好友列表 - 修复时间判断逻辑"""
        try:
            if (self.last_friend_check and 
                (datetime.now() - self.last_friend_check).total_seconds() < 600):  # 修复：使用total_seconds()
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
        """检查是否为好友"""
        await self._refresh_friend_list(client)
        return user_id in self.friend_list

    async def _auto_like_checker(self):
        """自动点赞检查器 - 优化定时逻辑，减少CPU消耗"""
        await asyncio.sleep(10)  # 初始延迟
        
        while True:
            try:
                # 每次检查前重新加载配置，检测配置变化
                await self.update_config_from_file()
                
                now = datetime.now()
                today = now.date().strftime("%Y-%m-%d")
                
                # 每次检查前先自动修复日期问题
                fix_result = await self.check_and_fix_date_issue()
                if fix_result:
                    logger.info(f"🔄 自动修复日期: {fix_result}")
                
                # 计算下次目标时间
                target_time = datetime(now.year, now.month, now.day, 
                                     self.auto_like_hour, self.auto_like_minute, self.auto_like_second)
                
                # 如果今天的目标时间已过，计算明天的时间
                if now >= target_time:
                    target_time += timedelta(days=1)
                
                # 计算等待时间
                wait_seconds = (target_time - now).total_seconds()
                
                # 如果等待时间较长，先等待到接近目标时间
                if wait_seconds > 60:  # 如果等待时间超过1分钟
                    logger.info(f"⏰ 下次自动点赞将在 {wait_seconds:.0f} 秒后执行")
                    # 等待到目标时间前1分钟，但最多等待1小时（避免配置更新不及时）
                    await asyncio.sleep(min(wait_seconds - 60, 3600))
                    continue
                
                # 接近目标时间，开始精确检查
                while wait_seconds > 0:
                    await asyncio.sleep(min(wait_seconds, 1))  # 最多等待1秒
                    now = datetime.now()
                    wait_seconds = (target_time - now).total_seconds()
                
                # 到达目标时间，执行自动点赞
                logger.info(f"🎯 触发自动点赞! 当前时间: {now.strftime('%H:%M:%S')}")
                
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
                                logger.info(f"开始执行自动点赞，目标用户: {len(friend_users)} 人")
                                
                                # 合并通知
                                complete_message = f"🤖 自动点赞执行完成\n⏰ 时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')}\n👥 成功点赞: {len(friend_users)} 人\n🔢 每人点赞: {self.likes_per_user} 次\n⏳ 下次点赞: {self.get_next_like_time()}"
                                await self.send_group_notification(complete_message)
                                
                                result = await self._like(client, friend_users)
                                
                                # 更新最后点赞日期
                                self.zanwo_date = today
                                self.config["zanwo_date"] = self.zanwo_date
                                self.config.save_config()
                                logger.info(f"✅ 已更新最后点赞日期为: {self.zanwo_date}")
                            else:
                                logger.warning("⚠️ 没有找到订阅的好友用户")
                                self.zanwo_date = today
                                self.config["zanwo_date"] = self.zanwo_date
                                self.config.save_config()
                            break
                
            except asyncio.CancelledError:
                logger.info("自动点赞任务被取消")
                break
            except Exception as e:
                logger.error(f"自动点赞检查失败: {e}")
                # 出错后等待一段时间再重试
                await asyncio.sleep(60)

    async def _like_single_user(self, client, user_id: str, username: str = "未知用户") -> str:
        """给单个用户点赞 - 核心点赞逻辑"""
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
                # 注意：通过错误消息字符串判断失败原因是脆弱的
                # 如果aiocqhttp库更新错误消息文本，此逻辑可能失效
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

    async def _like(self, client, ids: list[str]) -> str:
        """点赞的核心逻辑 - 重构以复用_like_single_user"""
        replys = []
        for user_id in ids:
            try:
                user_info = await client.get_stranger_info(user_id=int(user_id))
                username = user_info.get("nickname", "未知用户")
            except Exception:
                username = "未知用户"
            
            result = await self._like_single_user(client, user_id, username)
            replys.append(result)

        return "\n".join(replys).strip()

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
        """订阅点赞"""
        sender_id = event.get_sender_id()
        
        client = event.bot
        if not await self._is_friend(client, sender_id):
            yield event.plain_result("❌ 订阅失败\n💡 请先加我为好友再订阅自动点赞哦~")
            return
            
        if sender_id in self.subscribed_users:
            yield event.plain_result("ℹ️ 订阅状态\n💡 你已经订阅点赞了哦~")
            return
        
        self.subscribed_users.append(sender_id)
        self.config["subscribed_users"] = self.subscribed_users
        self.config.save_config()
        
        logger.info(f"用户 {sender_id} 订阅了自动点赞")
        
        # 订阅时自动检查日期问题
        fix_result = await self.check_and_fix_date_issue()
        
        auto_time = f"{self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}"
        next_time = self.get_next_like_time()
        
        response = f"✅ 订阅成功\n⏰ 自动点赞时间: {auto_time}\n⏳ 下次点赞: {next_time}\n🔢 每人点赞: {self.likes_per_user} 次\n💡 提示: 只有好友才能订阅自动点赞"
        if fix_result:
            response += f"\n{fix_result}"
        yield event.plain_result(response)

    @filter.command("取消订阅点赞")
    async def unsubscribe_like(self, event: AiocqhttpMessageEvent):
        """取消订阅点赞"""
        sender_id = event.get_sender_id()
        if sender_id not in self.subscribed_users:
            yield event.plain_result("ℹ️ 订阅状态\n💡 你还没有订阅点赞哦~")
            return
        
        self.subscribed_users.remove(sender_id)
        self.config["subscribed_users"] = self.subscribed_users
        self.config.save_config()
        
        logger.info(f"用户 {sender_id} 取消了自动点赞订阅")
        yield event.plain_result("✅ 取消订阅成功\n💡 我将不再自动给你点赞")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("调试信息")
    async def debug_info(self, event: AiocqhttpMessageEvent):
        """查看详细的调试信息"""
        now = datetime.now()
        today_date = now.date().strftime("%Y-%m-%d")
        
        # 精确到秒的时间匹配检查
        time_match = (
            now.hour == self.auto_like_hour and 
            now.minute == self.auto_like_minute and 
            now.second == self.auto_like_second
        )
        
        # 创建带时间的日期字符串用于显示
        last_like_datetime = f"{self.zanwo_date} {self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}"
        today_datetime = f"{today_date} {now.hour:02d}:{now.minute:02d}:{now.second:02d}"
        
        debug_info = f"🔍 调试信息\n当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}\n设置时间: {self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}\n时间匹配: {time_match}\n最后点赞日期: {last_like_datetime}\n今天日期: {today_datetime}\n日期不同: {self.zanwo_date != today_date}\n自动点赞启用: {self.auto_like_enabled}\n订阅用户数: {len(self.subscribed_users)}\n好友数: {len(self.friend_list)}\n通知群组: {len(self.notify_groups)}"
        
        should_auto_like = (
            self.auto_like_enabled and 
            len(self.subscribed_users) > 0 and 
            self.zanwo_date != today_date and
            time_match
        )
        
        debug_info += f"\n满足自动点赞条件: {should_auto_like}\n下次点赞: {self.get_next_like_time()}"
        
        yield event.plain_result(debug_info)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("点赞状态")
    async def like_status(self, event: AiocqhttpMessageEvent):
        """查看点赞插件状态"""
        auto_time = f"{self.auto_like_hour:02d}:{self.auto_like_minute:02d}:{self.auto_like_second:02d}"
        next_time = self.get_next_like_time()
        
        # 检查并修复日期问题
        fix_result = await self.check_and_fix_date_issue()
        
        status_info = f"🤖 点赞插件状态\n⏰ 自动点赞时间: {auto_time}\n⏳ 下次点赞: {next_time}\n📅 最后点赞日期: {self.zanwo_date}\n🔢 每人点赞: {self.likes_per_user} 次\n✅ 自动点赞: {'已开启' if self.auto_like_enabled else '已关闭'}\n👥 订阅用户: {len(self.subscribed_users)} 人\n📢 通知群组: {len(self.notify_groups)} 个"
        
        if fix_result:
            status_info += f"\n{fix_result}"
        
        yield event.plain_result(status_info)