"""
Telegram Bot 通知模块

提供通过Telegram Bot发送通知的功能
"""

import json
import logging
import requests
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, asdict


BEIJING_TZ = ZoneInfo("Asia/Shanghai")


@dataclass
class TaskResult:
    """任务执行结果"""

    task_type: str  # 任务类型：signin, reply, browse
    success: bool  # 是否成功
    message: str  # 结果消息
    details: Optional[str] = None  # 详细信息
    timestamp: Optional[str] = None  # 执行时间

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class ExecutionSummary:
    """执行摘要"""

    username: str
    start_time: str
    end_time: str
    total_duration: str
    tasks: List[TaskResult]
    overall_success: bool
    total_runs: int = 0

    def to_message(self) -> str:
        """转换为美观的Telegram消息格式"""
        status_emoji = "✅" if self.overall_success else "❌"
        status_text = "成功" if self.overall_success else "失败"

        # 统计任务结果
        success_count = sum(1 for task in self.tasks if task.success)
        total_count = len(self.tasks)

        message = f"""*98tang\\-autosign 执行报告*

*账号:* `{self.username}`
*日期:* `{self.start_time.split()[0]}`
*开始时间:* `{self.start_time.split()[1]}`
*结束时间:* `{self.end_time.split()[1]}`
*总耗时:* `{self.total_duration}`
*执行状态:* {status_emoji} *{status_text}*
*任务统计:* `{success_count}/{total_count}` 成功

*任务详情:*
"""

        for task in self.tasks:
            task_emoji = "✅" if task.success else "❌"
            task_name = {
                "signin": "签到",
                "reply": "回帖",
                "browse": "拟真浏览",
            }.get(task.task_type, task.task_type)

            message += f"{task_emoji} *{task_name}:* `{task.message}`\n"
            if task.details:
                # 转义特殊字符
                details_escaped = (
                    task.details.replace("_", "\\_")
                    .replace("*", "\\*")
                    .replace("[", "\\[")
                    .replace("]", "\\]")
                    .replace("(", "\\(")
                    .replace(")", "\\)")
                    .replace("~", "\\~")
                    .replace("`", "\\`")
                    .replace(">", "\\>")
                    .replace("#", "\\#")
                    .replace("+", "\\+")
                    .replace("-", "\\-")
                    .replace("=", "\\=")
                    .replace("|", "\\|")
                    .replace("{", "\\{")
                    .replace("}", "\\}")
                    .replace(".", "\\.")
                    .replace("!", "\\!")
                )
                message += f"  _{details_escaped}_\n"

        # 累计任务执行历史（由 GitHub Actions 持久化计数并传入）
        message += f"\n*任务历史:*\n总共执行{self.total_runs}次任务\n"

        return message.strip()


@dataclass
class NotificationData:
    """通知数据包"""

    message: str  # 主要消息内容
    attachments: List[Dict[str, Any]] = None  # 附件列表
    parse_mode: str = "MarkdownV2"  # 消息解析模式

    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []


class TelegramNotifier:
    """Telegram Bot 通知器"""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        proxy_url: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        初始化Telegram通知器

        Args:
            bot_token: Telegram Bot Token
            chat_id: Telegram Chat ID
            proxy_url: 代理URL（可选）
            logger: 日志器
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.proxy_url = proxy_url or "https://api.telegram.org"
        self.logger = logger or logging.getLogger(__name__)

        # 确保代理URL格式正确
        if not self.proxy_url.startswith("http"):
            self.proxy_url = f"https://{self.proxy_url}"

        # 移除尾部斜杠
        self.proxy_url = self.proxy_url.rstrip("/")

        self.api_url = f"{self.proxy_url}/bot{self.bot_token}"

        # 验证配置
        self._validate_config()

    def _validate_config(self) -> None:
        """验证配置"""
        if not self.bot_token:
            raise ValueError("Telegram Bot Token 不能为空")
        if not self.chat_id:
            raise ValueError("Telegram Chat ID 不能为空")

        self.logger.debug(f"Telegram通知器初始化完成，使用API: {self.proxy_url}")

    def send_message(self, message: str, parse_mode: str = "MarkdownV2") -> bool:
        """
        发送消息到Telegram

        Args:
            message: 要发送的消息
            parse_mode: 解析模式 (Markdown/HTML)

        Returns:
            是否发送成功
        """
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode,
            }

            self.logger.debug(f"发送Telegram消息: {message[:100]}...")

            response = requests.post(url, json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    self.logger.debug("Telegram消息发送成功")
                    return True
                else:
                    self.logger.error(
                        f"Telegram API返回错误: {result.get('description', '未知错误')}"
                    )
                    return False
            else:
                self.logger.error(
                    f"Telegram消息发送失败，HTTP状态码: {response.status_code}"
                )
                self.logger.debug(f"响应内容: {response.text}")
                return False

        except requests.exceptions.Timeout:
            self.logger.error("Telegram消息发送超时")
            return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Telegram消息发送失败: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Telegram消息发送异常: {e}")
            return False

    def send_summary(self, summary: ExecutionSummary) -> bool:
        """
        发送执行摘要

        Args:
            summary: 执行摘要

        Returns:
            是否发送成功
        """
        return self.send_message(summary.to_message())

    def send_log_file(self, log_file_path: str) -> bool:
        """
        发送日志文件

        Args:
            log_file_path: 日志文件路径

        Returns:
            是否发送成功
        """
        try:
            if not os.path.exists(log_file_path):
                self.logger.error(f"日志文件不存在: {log_file_path}")
                return False

            url = f"{self.api_url}/sendDocument"

            with open(log_file_path, "rb") as f:
                files = {"document": f}
                data = {
                    "chat_id": self.chat_id,
                    "caption": f'📄 *98tang\\-autosign 日志文件*\n\n📅 生成时间: `{datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")}`',
                    "parse_mode": "MarkdownV2",
                }

                self.logger.debug(f"发送日志文件: {log_file_path}")

                response = requests.post(url, files=files, data=data, timeout=60)

                if response.status_code == 200:
                    result = response.json()
                    if result.get("ok"):
                        self.logger.debug("日志文件发送成功")
                        return True
                    else:
                        self.logger.error(
                            f"Telegram API返回错误: {result.get('description', '未知错误')}"
                        )
                        return False
                else:
                    self.logger.error(
                        f"日志文件发送失败，HTTP状态码: {response.status_code}"
                    )
                    self.logger.debug(f"响应内容: {response.text}")
                    return False

        except requests.exceptions.Timeout:
            self.logger.error("日志文件发送超时")
            return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"日志文件发送失败: {e}")
            return False
        except Exception as e:
            self.logger.error(f"日志文件发送异常: {e}")
            return False

    def test_connection(self) -> bool:
        """
        测试连接

        Returns:
            是否连接成功
        """
        test_message = f"""
🧪 *98tang\\-autosign 连接测试*

✅ Telegram Bot 连接正常
⏰ 测试时间: `{datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")}`

如果您看到这条消息，说明通知配置成功！
"""

        return self.send_message(test_message.strip())

    def send_document(self, document_path: str, caption: str = None) -> bool:
        """
        发送文档文件

        Args:
            document_path: 文档文件路径
            caption: 文档说明（可选）

        Returns:
            是否发送成功
        """
        try:
            if not os.path.exists(document_path):
                self.logger.error(f"文档文件不存在: {document_path}")
                return False

            url = f"{self.api_url}/sendDocument"

            with open(document_path, "rb") as f:
                files = {"document": f}
                data = {
                    "chat_id": self.chat_id,
                }

                # 如果提供了说明，添加到请求中
                if caption:
                    # 转义MarkdownV2格式的特殊字符
                    def escape_markdown_v2(text):
                        special_chars = [
                            "_",
                            "*",
                            "[",
                            "]",
                            "(",
                            ")",
                            "~",
                            "`",
                            ">",
                            "#",
                            "+",
                            "-",
                            "=",
                            "|",
                            "{",
                            "}",
                            ".",
                            "!",
                        ]
                        for char in special_chars:
                            text = text.replace(char, f"\\{char}")
                        return text

                    data["caption"] = escape_markdown_v2(caption)
                    data["parse_mode"] = "MarkdownV2"

                self.logger.debug(f"发送文档: {document_path}")

                response = requests.post(url, files=files, data=data, timeout=60)

                if response.status_code == 200:
                    result = response.json()
                    if result.get("ok"):
                        self.logger.debug("文档发送成功")
                        return True
                    else:
                        self.logger.error(
                            f"Telegram API返回错误: {result.get('description', '未知错误')}"
                        )
                        return False
                else:
                    self.logger.error(
                        f"文档发送失败，HTTP状态码: {response.status_code}"
                    )
                    self.logger.debug(f"响应内容: {response.text}")
                    return False

        except requests.exceptions.Timeout:
            self.logger.error("文档发送超时")
            return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"文档发送失败: {e}")
            return False
        except Exception as e:
            self.logger.error(f"文档发送异常: {e}")
            return False

    def send_error(self, error_message: str, error_type: str = "程序错误") -> bool:
        """
        发送错误通知

        Args:
            error_message: 错误消息
            error_type: 错误类型

        Returns:
            是否发送成功
        """
        # 转义特殊字符
        escaped_error = (
            error_message.replace("_", "\\_")
            .replace("*", "\\*")
            .replace("[", "\\[")
            .replace("]", "\\]")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("~", "\\~")
            .replace("`", "\\`")
            .replace(">", "\\>")
            .replace("#", "\\#")
            .replace("+", "\\+")
            .replace("-", "\\-")
            .replace("=", "\\=")
            .replace("|", "\\|")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace(".", "\\.")
            .replace("!", "\\!")
        )
        escaped_type = (
            error_type.replace("_", "\\_")
            .replace("*", "\\*")
            .replace("[", "\\[")
            .replace("]", "\\]")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("~", "\\~")
            .replace("`", "\\`")
            .replace(">", "\\>")
            .replace("#", "\\#")
            .replace("+", "\\+")
            .replace("-", "\\-")
            .replace("=", "\\=")
            .replace("|", "\\|")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace(".", "\\.")
            .replace("!", "\\!")
        )

        message = f"""
🚨 *98tang\\-autosign 错误报告*

❌ *错误类型*: `{escaped_type}`
⏰ *时间*: `{datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")}`

📋 *错误详情*:
```
{escaped_error}
```
"""

        return self.send_message(message.strip())

    def send_screenshot(self, screenshot_path: str, caption: str = None) -> bool:
        """
        发送截图

        Args:
            screenshot_path: 截图文件路径
            caption: 自定义说明文字（可选）

        Returns:
            是否发送成功
        """
        try:
            if not os.path.exists(screenshot_path):
                self.logger.error(f"截图文件不存在: {screenshot_path}")
                return False

            url = f"{self.api_url}/sendPhoto"

            with open(screenshot_path, "rb") as f:
                files = {"photo": f}
                # 使用自定义caption或默认caption
                if caption is None:
                    caption = f'📸 *错误截图*\n\n⏰ 捕获时间: `{datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")}`'

                data = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "MarkdownV2",
                }

                self.logger.debug(f"发送错误截图: {screenshot_path}")

                response = requests.post(url, files=files, data=data, timeout=60)

                if response.status_code == 200:
                    result = response.json()
                    if result.get("ok"):
                        self.logger.debug("错误截图发送成功")
                        return True
                    else:
                        self.logger.error(
                            f"Telegram API返回错误: {result.get('description', '未知错误')}"
                        )
                        return False
                else:
                    self.logger.error(
                        f"错误截图发送失败，HTTP状态码: {response.status_code}"
                    )
                    self.logger.debug(f"响应内容: {response.text}")
                    return False

        except requests.exceptions.Timeout:
            self.logger.error("错误截图发送超时")
            return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"错误截图发送失败: {e}")
            return False
        except Exception as e:
            self.logger.error(f"错误截图发送异常: {e}")
            return False

    def send_html_file(self, html_path: str) -> bool:
        """
        发送HTML源代码文件

        Args:
            html_path: HTML文件路径

        Returns:
            是否发送成功
        """
        caption = f'📄 错误HTML源代码\n\n⏰ 捕获时间: {datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")}'
        return self.send_document(html_path, caption)

    def send_batch_notification(self, notification_data: NotificationData) -> bool:
        """
        发送批量通知（统一发送消息和附件）

        Args:
            notification_data: 通知数据包

        Returns:
            是否发送成功（主消息发送成功即认为整体成功，附件失败不影响整体结果）
        """
        try:
            # 首先发送主消息
            success = self.send_message(
                notification_data.message, notification_data.parse_mode
            )

            if not success:
                self.logger.error("发送主通知消息失败")
                return False

            self.logger.info("主通知消息发送成功")

            # 按顺序发送附件（附件失败不影响整体成功状态）
            successful_attachments = 0
            failed_attachments = 0

            for attachment in notification_data.attachments:
                attachment_type = attachment.get("type", "")
                file_path = attachment.get("path", "")
                caption = attachment.get("caption", "")

                if not file_path:
                    self.logger.warning(f"附件路径为空，跳过: {attachment_type}")
                    failed_attachments += 1
                    continue

                if not os.path.exists(file_path):
                    self.logger.warning(f"附件文件不存在，跳过: {file_path}")
                    failed_attachments += 1
                    continue

                try:
                    attachment_sent = False
                    if attachment_type == "screenshot":
                        attachment_sent = self.send_screenshot(file_path, caption)
                    elif attachment_type == "log":
                        attachment_sent = self.send_log_file(file_path)
                    elif attachment_type == "html":
                        attachment_sent = self.send_html_file(file_path)
                    elif attachment_type == "document":
                        attachment_sent = self.send_document(file_path, caption)
                    else:
                        self.logger.warning(f"未知的附件类型，跳过: {attachment_type}")
                        failed_attachments += 1
                        continue

                    if attachment_sent:
                        self.logger.debug(
                            f"附件发送成功 ({attachment_type}): {file_path}"
                        )
                        successful_attachments += 1
                    else:
                        self.logger.warning(
                            f"附件发送失败 ({attachment_type}): {file_path}"
                        )
                        failed_attachments += 1

                except Exception as attachment_error:
                    self.logger.warning(
                        f"发送附件异常 ({attachment_type}: {file_path}): {attachment_error}"
                    )
                    failed_attachments += 1

            # 记录附件发送统计
            total_attachments = len(notification_data.attachments)
            if total_attachments > 0:
                self.logger.info(
                    f"附件发送完成: {successful_attachments}/{total_attachments} 成功"
                )
                if failed_attachments > 0:
                    self.logger.warning(
                        f"有 {failed_attachments} 个附件发送失败，但主消息已成功发送"
                    )

            # 只要主消息发送成功，就认为整体成功
            return success

        except Exception as e:
            self.logger.error(f"批量通知发送失败: {e}")
            return False

    def create_error_notification(
        self,
        error_message: str,
        error_type: str = "程序错误",
        log_file_path: Optional[str] = None,
        screenshot_path: Optional[str] = None,
        html_path: Optional[str] = None,
        include_live_screenshot: bool = False,
        live_screenshot_context: Optional[str] = None,
    ) -> NotificationData:
        """
        创建错误通知数据包

        Args:
            error_message: 错误消息
            error_type: 错误类型
            log_file_path: 日志文件路径（可选）
            screenshot_path: 截图文件路径（可选）
            html_path: HTML文件路径（可选）
            include_live_screenshot: 是否包含实时截图说明
            live_screenshot_context: 实时截图上下文信息

        Returns:
            NotificationData: 通知数据包
        """
        # 转义特殊字符
        escaped_error = self._escape_markdown_v2(error_message)
        escaped_type = self._escape_markdown_v2(error_type)

        # 构建主消息
        message = f"""🚨 *98tang\\-autosign 错误报告*

❌ *错误类型*: `{escaped_type}`
⏰ *时间*: `{datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")}`

📋 *错误详情*:
```
{escaped_error}
```"""

        # 添加附件信息说明
        attachments = []
        attachment_descriptions = []

        if log_file_path and os.path.exists(log_file_path):
            attachments.append(
                {
                    "type": "log",
                    "path": log_file_path,
                    "caption": f'📄 *98tang\\-autosign 错误日志*\n\n📅 生成时间: `{datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")}`',
                }
            )
            attachment_descriptions.append("📄 错误日志文件")

        if screenshot_path and os.path.exists(screenshot_path):
            attachments.append(
                {
                    "type": "screenshot",
                    "path": screenshot_path,
                    "caption": f'📸 *错误截图*\n\n⏰ 捕获时间: `{datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")}`',
                }
            )
            attachment_descriptions.append("📸 错误截图")

        if html_path and os.path.exists(html_path):
            attachments.append(
                {
                    "type": "html",
                    "path": html_path,
                    "caption": f'📄 错误HTML源代码\n\n⏰ 捕获时间: `{datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")}`',
                }
            )
            attachment_descriptions.append("📄 HTML源代码")

        # 记录附件处理结果
        if attachments:
            self.logger.debug(f"错误通知准备了 {len(attachments)} 个附件")
        else:
            self.logger.debug("错误通知没有附件")

        if include_live_screenshot and live_screenshot_context:
            escaped_context = self._escape_markdown_v2(live_screenshot_context)
            attachment_descriptions.append(f"📱 实时截图 \\({escaped_context}\\)")

        # 如果有附件，添加附件说明
        if attachment_descriptions:
            message += f"\n\n📎 *附件内容*:\n"
            for desc in attachment_descriptions:
                message += f"• {desc}\n"

        return NotificationData(
            message=message.strip(), attachments=attachments, parse_mode="MarkdownV2"
        )

    def create_success_notification(
        self,
        summary: ExecutionSummary,
        log_file_path: Optional[str] = None,
        include_live_screenshot: bool = False,
        live_screenshot_context: Optional[str] = None,
    ) -> NotificationData:
        """
        创建成功通知数据包

        Args:
            summary: 执行摘要
            log_file_path: 日志文件路径（可选）
            include_live_screenshot: 是否包含实时截图说明
            live_screenshot_context: 实时截图上下文信息

        Returns:
            NotificationData: 通知数据包
        """
        # 使用现有的摘要格式作为主消息
        message = summary.to_message()

        # 添加附件
        attachments = []
        attachment_descriptions = []

        # 安全地处理日志文件附件
        if log_file_path:
            try:
                if os.path.exists(log_file_path):
                    attachments.append(
                        {
                            "type": "log",
                            "path": log_file_path,
                            "caption": f'📄 *98tang\\-autosign 日志*\n\n📅 生成时间: `{datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")}`',
                        }
                    )
                    attachment_descriptions.append("📄 执行日志文件")
                else:
                    self.logger.warning(f"日志文件不存在，跳过附件: {log_file_path}")
            except Exception as e:
                self.logger.warning(f"处理日志文件附件时出错: {e}")

        if include_live_screenshot and live_screenshot_context:
            escaped_context = self._escape_markdown_v2(live_screenshot_context)
            attachment_descriptions.append(f"📱 成功截图 \\({escaped_context}\\)")

        # 如果有附件，添加附件说明
        if attachment_descriptions:
            message += f"\n\n📎 *附件内容*:\n"
            for desc in attachment_descriptions:
                message += f"• {desc}\n"

        return NotificationData(
            message=message.strip(), attachments=attachments, parse_mode="MarkdownV2"
        )

    def _escape_markdown_v2(self, text: str) -> str:
        """转义MarkdownV2格式的特殊字符"""
        special_chars = [
            "_",
            "*",
            "[",
            "]",
            "(",
            ")",
            "~",
            "`",
            ">",
            "#",
            "+",
            "-",
            "=",
            "|",
            "{",
            "}",
            ".",
            "!",
        ]
        for char in special_chars:
            text = text.replace(char, f"\\{char}")
        return text
