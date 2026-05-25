"""
核心消息处理器 - 机器人主要逻辑
"""
import re
import logging
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import Database
from config import ADMIN_USER_IDS, BOT_USERNAME
from accounting import AccountingManager
from bill_formatter import BillFormatter
from price_checker import PriceChecker

logger = logging.getLogger(__name__)
db = Database.get_instance()
acc_mgr = AccountingManager()
bill_fmt = BillFormatter()
price_ck = PriceChecker()


class BotHandler:
    """机器人消息处理"""

    def __init__(self):
        # 群组设置缓存
        self._cache = {}

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理所有文本消息"""
        if not update.message or not update.message.text:
            return

        msg = update.message
        chat_id = msg.chat_id
        user_id = msg.from_user.id
        text = msg.text.strip()
        message_id = msg.message_id
        chat_type = msg.chat.type
        is_group = chat_type != "private"

        user = self._get_or_create_user(msg.from_user)
        group = self._get_or_create_group(msg.chat) if is_group else None

        # 处理新成员加入（机器人被拉入群）
        if is_group and msg.new_chat_members:
            for member in msg.new_chat_members:
                if member.id == context.bot.id:
                    await self._on_bot_joined(update, context, group)
                    return

            # 检查记账是否开启
            if is_group and not self._is_accounting_enabled(group["id"]):
                activation_cmds = ["/start", "开始", "开始记账", "激活记账", "激活", "启用记账"]
                if text not in activation_cmds:
                    await msg.reply_text(
                        "⚠️ 记账功能未开启\n\n请输入 <b>开始</b> 开始记账\n"
                        "每日默认记账周期：凌晨4点至第二天凌晨4点",
                        parse_mode=ParseMode.HTML,
                    )
                    return

        # 路由消息
        if text.startswith("/"):
            await self._route_command(update, context, text, user, group)
        else:
            await self._route_text(update, context, text, user, group, message_id)

    async def _route_command(self, update, context, text, user, group):
        """斜杠命令路由"""
        chat_id = update.effective_chat.id
        parts = text.split(" ", 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "/start":
            await self._cmd_start(update, context, user, group)
        elif cmd == "/set" and group:
            await self._cmd_set_fee(update, context, user, group, args)
        elif cmd == "/gd" and group:
            await self._cmd_fix_rate(update, context, user, group, args)
        elif cmd == "/usdt" and group:
            await self._cmd_usdt_price(update, context)
        elif cmd == "/help":
            await self._cmd_help(update, context)

    async def _route_text(self, update, context, text, user, group, message_id):
        """普通文本路由"""
        chat_id = update.effective_chat.id

        # 币价查询
        if self._is_price_cmd(text):
            await self._handle_price(update, context, text)
            return

        # 记账命令
        if self._is_accounting_cmd(text):
            if group:
                await self._handle_accounting(update, context, text, user, group, message_id)
            else:
                await update.message.reply_text("记账功能只能在群组中使用！")
            return

        # 纠错命令
        if self._is_correction_cmd(text):
            if group:
                await self._handle_correction(update, context, text, user, group, message_id)
            return

        # 激活/配置命令
        if self._is_activation_or_config(text):
            await self._handle_activation_config(update, context, text, user, group)
            return

        # 操作员管理
        if self._is_operator_cmd(text):
            await self._handle_operator(update, context, text, user, group, message_id)
            return

        # 查询命令
        if self._is_query_cmd(text):
            await self._handle_query(update, context, text, user, group)
            return

    # ===================== 币价 =====================

    def _is_price_cmd(self, text: str) -> bool:
        t = text.lower()
        return t in ("lk", "lz", "lw") or bool(re.match(r"^[kzw]\d+(\.\d+)?$", t))

    async def _handle_price(self, update, context, text):
        chat_id = update.effective_chat.id
        t = text.lower()

        price_map = {
            "lk": ("💳 银行卡", price_ck.get_bank_card_price),
            "lz": ("💙 支付宝", price_ck.get_alipay_price),
            "lw": ("💚 微信", price_ck.get_wechat_price),
        }

        if t in price_map:
            label, func = price_map[t]
            r = func()
            if r:
                msg = f"<b>{label} 欧易实时价格</b>\n━━━━━━━━━━━━━\n买入价：{r['buy']} CNY\n卖出价：{r['sell']} CNY"
            else:
                msg = "❌ 获取价格失败"
            await context.bot.send_message(chat_id, msg, parse_mode=ParseMode.HTML)
            return

        # k100 / z100 / w100 换算
        m = re.match(r"^([kzw])([\d\.]+)$", t)
        if m:
            ptype, amount_str = m.group(1), m.group(2)
            amount = float(amount_str)

            type_map = {
                "k": ("银行卡", price_ck.get_bank_card_price),
                "z": ("支付宝", price_ck.get_alipay_price),
                "w": ("微信", price_ck.get_wechat_price),
            }
            label, func = type_map[ptype]
            r = func()
            if r:
                buy = float(r["buy"])
                usdt = round(amount / buy, 2) if buy > 0 else 0
                msg = f"<b>💱 {label} USDT换算</b>\n━━━━━━━━━━━━━\n{amount} CNY ÷ {buy} = <b>{usdt} USDT</b>"
            else:
                msg = f"❌ 获取{label}价格失败"
            await context.bot.send_message(chat_id, msg, parse_mode=ParseMode.HTML)

    # ===================== 记账 =====================

    def _is_accounting_cmd(self, text: str) -> bool:
        return bool(re.match(r"^[+\-][\d\.,]+", text)) or text.startswith("下发") or text == "撤销"

    async def _handle_accounting(self, update, context, text, user, group, message_id):
        chat_id = update.effective_chat.id
        if not self._has_permission(user, group):
            await update.message.reply_text("❌ 您没有记账权限！")
            return

        result = acc_mgr.parse_command(text, group["id"])
        if not result["success"]:
            await update.message.reply_text(f"❌ {result['error']}")
            return

        txn_id = acc_mgr.execute_transaction(result["data"], user, group, message_id)
        if txn_id:
            await self._send_bill(update, context, group)
        else:
            await update.message.reply_text("❌ 记账操作失败！")

    # ===================== 纠错 =====================

    def _is_correction_cmd(self, text: str) -> bool:
        return text.startswith("入款-") or text.startswith("下发-")

    async def _handle_correction(self, update, context, text, user, group, message_id):
        chat_id = update.effective_chat.id
        if not self._has_permission(user, group):
            await update.message.reply_text("❌ 您没有权限！")
            return

        result = acc_mgr.parse_correction(text, group["id"])
        if not result["success"]:
            await update.message.reply_text(f"❌ {result['error']}")
            return

        txn_id = acc_mgr.execute_transaction(result["data"], user, group, message_id)
        if txn_id:
            await self._send_bill(update, context, group)
        else:
            await update.message.reply_text("❌ 修正操作失败！")

    # ===================== 激活/配置 =====================

    def _is_activation_or_config(self, text: str) -> bool:
        activation = {"开始", "开始记账", "激活记账", "激活", "启用记账",
                       "结束记录", "结束记账", "关闭记账"}
        return text in activation or text.startswith("设置") or text in ("配置", "费率") or text.startswith("清理今天数据")

    async def _handle_activation_config(self, update, context, text, user, group):
        chat_id = update.effective_chat.id

        # 开始记账（4am 周期）
        if text in ("开始", "开始记账", "激活记账", "激活", "启用记账"):
            await self._activate_daily(update, context, group)
            return

        # 结束记账
        if text in ("结束记录", "结束记账", "关闭记账"):
            if not self._has_permission(user, group):
                await update.message.reply_text("❌ 无权限！")
                return
            self._set_setting(group["id"], "accounting_status", False)
            await update.message.reply_text("✅ 记账功能已关闭")
            return

        # 清理今天数据
        if text.startswith("清理今天数据"):
            if user["telegram_id"] not in ADMIN_USER_IDS and user["permission_level"] > 1:
                await update.message.reply_text("❌ 只有管理员才能清理数据！")
                return
            await self._clear_today(update, context, user, group)
            return

        # 以下需要操作员权限
        if not self._has_permission(user, group):
            await update.message.reply_text("❌ 您没有配置权限！")
            return

        # 查看配置
        if text in ("配置", "费率"):
            await self._show_config(update, context, group)
            return

        # 设置费率
        m = re.match(r"^设置费率([\d\.]+)%?$", text)
        if m:
            rate = float(m.group(1))
            self._set_setting(group["id"], "fee_rate", str(rate))
            await update.message.reply_text(f"✅ 费率已设置为 {rate}%")
            return

        # 设置汇率
        m = re.match(r"^设置汇率([\d\.]+)$", text)
        if m:
            rate = float(m.group(1))
            self._set_setting(group["id"], "exchange_rate", str(rate))
            await update.message.reply_text(f"✅ 汇率已设置为 {rate}")
            return

        # 美元汇率
        m = re.match(r"^设置美元汇率([\d\.]+)$", text)
        if m:
            rate = float(m.group(1))
            if rate == 0:
                self._del_custom_rate(group["id"], "美元")
                await update.message.reply_text("✅ 美元汇率已隐藏")
            else:
                self._set_custom_rate(group["id"], "美元", None, rate)
                await update.message.reply_text(f"✅ 美元汇率已设置为 {rate}")
            return

        # 比索汇率
        m = re.match(r"^设置比索汇率([\d\.]+)$", text)
        if m:
            rate = float(m.group(1))
            if rate == 0:
                self._del_custom_rate(group["id"], "比索")
                await update.message.reply_text("✅ 比索汇率已隐藏")
            else:
                self._set_custom_rate(group["id"], "比索", None, rate)
                await update.message.reply_text(f"✅ 比索汇率已设置为 {rate}")
            return

        # 显示模式
        if text == "设置为计数模式":
            self._set_setting(group["id"], "display_mode", "count")
            await update.message.reply_text("✅ 已设置为计数模式（简洁模式）")
            return

        m = re.match(r"^设置显示模式(\d+)$", text)
        if m:
            mode = m.group(1)
            mode_desc = {"1": "原始", "2": "3条", "3": "1条", "4": "仅总入款"}.get(mode, f"模式{mode}")
            self._set_setting(group["id"], "display_mode", mode)
            await update.message.reply_text(f"✅ 已设置为显示模式{mode}（{mode_desc}）")
            return

        if text == "设置为原始模式":
            self._set_setting(group["id"], "display_mode", "1")
            await update.message.reply_text("✅ 已设置为原始模式")
            return

        # 实时汇率源
        if text == "设置火币汇率":
            self._set_setting(group["id"], "rate_source", "huobi")
            await update.message.reply_text("✅ 已设置使用火币实时汇率")
            return
        if text == "设置欧易汇率":
            self._set_setting(group["id"], "rate_source", "okx")
            await update.message.reply_text("✅ 已设置使用欧易实时汇率")
            return

        # 自定义汇率/美元费率
        m = re.match(r"^设置(.+)费率([\d\.]+)$", text)
        if m:
            name, rate = m.group(1).strip(), float(m.group(2))
            self._set_custom_rate(group["id"], name, rate, None)
            await update.message.reply_text(f"✅ {name}费率已设置为 {rate}%")
            return
        m = re.match(r"^设置(.+)汇率([\d\.]+)$", text)
        if m:
            name, rate = m.group(1).strip(), float(m.group(2))
            self._set_custom_rate(group["id"], name, None, rate)
            await update.message.reply_text(f"✅ {name}汇率已设置为 {rate}")
            return

        await update.message.reply_text("❌ 无法识别的配置命令")

    # ===================== 操作员管理 =====================

    def _is_operator_cmd(self, text: str) -> bool:
        return (text.startswith("设置操作人") or
                "添加操作员" in text or
                text.startswith("删除操作人") or
                "删除操作员" in text or
                text in ("显示操作人", "显示操作员", "设置为操作人"))

    async def _handle_operator(self, update, context, text, user, group, message_id):
        chat_id = update.effective_chat.id
        if not self._has_permission(user, group) and user["telegram_id"] not in ADMIN_USER_IDS:
            await update.message.reply_text("❌ 您没有管理权限！")
            return

        # 回复某人"设置为操作人"
        if text == "设置为操作人" and update.message.reply_to_message:
            target = update.message.reply_to_message.from_user
            await self._add_operator_by_user(update, context, group, target)
            return

        # 设置操作人 @xxx @yyy
        m = re.match(r"^设置操作人\s+(.+)$", text)
        if m:
            usernames = re.findall(r"@(\w+)", m.group(1))
            if usernames:
                added = 0
                for uname in usernames:
                    if self._add_operator_by_username(group, uname, user):
                        added += 1
                if added > 0:
                    await update.message.reply_text(f"✅ 已添加 {added} 位操作人")
                return
            await update.message.reply_text("❌ 请使用 @用户名 格式")
            return

        # 删除操作人 @xxx
        m = re.match(r"^删除操作人\s+@(\w+)", text)
        if m:
            await self._remove_operator(update, context, group, m.group(1))
            return

        # 旧格式兼容
        m = re.match(r"^@(\w+)\s+添加操作员$", text)
        if m:
            self._add_operator_by_username(group, m.group(1), user)
            await update.message.reply_text(f"✅ 已将 @{m.group(1)} 添加为操作人")
            return

        m = re.match(r"^@(\w+)\s+删除操作员$", text)
        if m:
            await self._remove_operator(update, context, group, m.group(1))
            return

        # 显示操作人
        if text in ("显示操作人", "显示操作员"):
            ops = db.query(
                "SELECT u.*, go.created_at as added_at FROM users u JOIN group_operators go ON u.id=go.user_id WHERE go.group_id=%s ORDER BY go.created_at",
                (group["id"],),
            )
            if not ops:
                await update.message.reply_text("📝 当前没有操作人\n\n💡 使用：设置操作人 @用户名")
                return
            lines = ["<b>👥 操作人列表</b>", "━━━━━━━━━━━━━"]
            for i, op in enumerate(ops, 1):
                name = f"@{op['username']}" if op["username"] else (op.get("first_name") or f"User#{op['telegram_id']}")
                lines.append(f"{i}. {name}")
            lines.append(f"\n共 {len(ops)} 位操作人")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    # ===================== 查询 =====================

    def _is_query_cmd(self, text: str) -> bool:
        return text in ("显示账单", "显示完整账单", "账单", "总账单", "上个月总账单", "我的账单", "重置", "清零", "清空", "删除账单", "结束账单")

    async def _handle_query(self, update, context, text, user, group):
        chat_id = update.effective_chat.id

        if text == "显示账单":
            await self._show_recent_bill(update, context, group)
            return

        if text == "显示完整账单":
            await self._show_full_bill_link(update, context, group)
            return

        if text == "账单":
            await self._send_regular_bill(update, context, group)
            return

        if text == "总账单":
            await self._show_monthly_bill(update, context, group)
            return

        if text == "上个月总账单":
            await self._show_prev_month_bill(update, context, group)
            return

        if text == "我的账单":
            if self._has_permission(user, group):
                await self._show_operator_bill(update, context, user, group)
            return

        if text in ("重置", "清零", "清空", "删除账单", "结束账单"):
            if self._has_permission(user, group):
                await self._reset_bill(update, context, user, group)
            else:
                await update.message.reply_text("❌ 无权限！")

    # ===================== 功能实现 =====================

    async def _on_bot_joined(self, update, context, group):
        chat_id = update.effective_chat.id
        self._set_setting(group["id"], "accounting_enabled", "0")
        self._set_setting(group["id"], "setup_completed", "0")

        msg = ("🤖 <b>记账机器人已加入群组！</b>\n\n"
               "📋 使用步骤：\n"
               "1️⃣ 输入 <b>开始</b> 激活记账\n"
               "2️⃣ 输入 <b>设置费率X%</b>\n"
               "3️⃣ 输入 <b>设置美元汇率6.5</b>\n\n"
               "📅 默认记账周期：凌晨4点至第二天凌晨4点")
        await context.bot.send_message(chat_id, msg, parse_mode=ParseMode.HTML)

    async def _activate_daily(self, update, context, group):
        chat_id = update.effective_chat.id
        now = datetime.now()
        today_4am = now.replace(hour=4, minute=0, second=0, microsecond=0)

        if now.hour < 4:
            period_start = today_4am - timedelta(days=1)
        else:
            period_start = today_4am
        period_end = period_start + timedelta(days=1)

        self._set_setting(group["id"], "accounting_status", True)
        self._set_setting(group["id"], "period_start", period_start.strftime("%Y-%m-%d %H:%M:%S"))
        self._set_setting(group["id"], "period_end", period_end.strftime("%Y-%m-%d %H:%M:%S"))
        self._set_setting(group["id"], "setup_completed", "1")

        bill_fmt.set_group_telegram_id(group["id"], chat_id)

        msg = (f"✅ <b>记账开始！</b>\n\n"
               f"📅 记账周期：{period_start.strftime('%m-%d %H:%M')} ~ {period_end.strftime('%m-%d %H:%M')}\n"
               f"💡 现在可以使用记账命令了")
        await context.bot.send_message(chat_id, msg, parse_mode=ParseMode.HTML)

    async def _clear_today(self, update, context, user, group):
        chat_id = update.effective_chat.id
        ps, pe = self._get_period(group)

        cnt = db.query_one(
            "SELECT COUNT(*) as cnt FROM transactions WHERE group_id=%s AND is_deleted=0 AND created_at BETWEEN %s AND %s",
            (group["id"], ps, pe),
        )["cnt"]
        if cnt == 0:
            await update.message.reply_text("⚠️ 当前周期无数据")
            return

        db.execute(
            "UPDATE transactions SET is_deleted=1 WHERE group_id=%s AND is_deleted=0 AND created_at BETWEEN %s AND %s",
            (group["id"], ps, pe),
        )
        name = self._display_name(user)
        await update.message.reply_text(f"✅ 已清理 {cnt} 条数据\n👤 {name}\n⚠️ 此操作不可恢复！")

    async def _show_recent_bill(self, update, context, group):
        chat_id = update.effective_chat.id
        ps, pe = self._get_period(group)

        rows = db.query(
            """SELECT t.*, u.username, u.first_name FROM transactions t
               LEFT JOIN users u ON t.user_id=u.id
               WHERE t.group_id=%s AND t.is_deleted=0
               AND t.created_at BETWEEN %s AND %s
               ORDER BY t.created_at DESC LIMIT 5""",
            (group["id"], ps, pe),
        )
        if not rows:
            await update.message.reply_text(
                f"📝 暂无记录\n📅 {ps} ~ {pe}",
                parse_mode=ParseMode.HTML,
            )
            return

        icons = {"income": "💰", "expense": "💸", "distribution": "📤", "correction": "🔧"}
        names = {"income": "入款", "expense": "出款", "distribution": "下发", "correction": "修正"}
        lines = ["<b>📋 最近账单</b>", "━━━━━━━━━━━━━"]
        for i, r in enumerate(rows, 1):
            icon = icons.get(r["transaction_type"], "📊")
            nm = names.get(r["transaction_type"], r["transaction_type"])
            amt = f"{r['amount']:.2f}"
            t = r["created_at"].strftime("%H:%M")
            lines.append(f"{i}. {icon} {nm} {amt} - {t}")

        await context.bot.send_message(chat_id, "\n".join(lines), parse_mode=ParseMode.HTML)

    async def _show_full_bill_link(self, update, context, group):
        chat_id = update.effective_chat.id
        base_url = bill_fmt.get_base_url()
        token = bill_fmt.get_group_token(group["id"])

        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        url_t = f"{base_url}/bill_detail?token={token}&group_id={group['id']}&date={today}"
        url_y = f"{base_url}/bill_detail?token={token}&group_id={group['id']}&date={yesterday}"

        msg = "<b>📊 完整账单</b>\n━━━━━━━━━━━━━\n\n🟢 今天账单\n🟡 昨天账单"
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 今天账单", url=url_t),
                InlineKeyboardButton("📋 昨天账单", url=url_y),
            ]
        ])
        await context.bot.send_message(chat_id, msg, reply_markup=kb, parse_mode=ParseMode.HTML)

    async def _send_regular_bill(self, update, context, group):
        chat_id = update.effective_chat.id
        bill_text = bill_fmt.generate_bill(group["id"])
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("📊 查看详情", url=f"{bill_fmt.get_base_url()}/bill_detail?token={bill_fmt.get_group_token(group['id'])}&group_id={group['id']}")
        ]])
        await context.bot.send_message(chat_id, bill_text, reply_markup=kb, parse_mode=ParseMode.HTML)

    async def _show_config(self, update, context, group):
        chat_id = update.effective_chat.id
        fee_rate = self._get_setting(group["id"], "fee_rate", "10")
        exchange_rate = self._get_setting(group["id"], "exchange_rate", "7.2")
        rate_source = self._get_setting(group["id"], "rate_source", "manual")
        display_mode = self._get_setting(group["id"], "display_mode", "1")

        src_map = {"manual": "手动", "huobi": "火币", "okx": "欧易", "fixed": "固定"}
        mode_map = {"count": "计数模式", "1": "原始模式", "2": "3条", "3": "1条", "4": "仅总入款"}

        lines = ["<b>⚙️ 当前配置</b>", "━━━━━━━━━━━━━"]
        lines.append(f"📊 费率：{fee_rate}%")
        lines.append(f"💱 汇率：{exchange_rate}")
        lines.append(f"🔄 汇率来源：{src_map.get(rate_source, rate_source)}")
        lines.append(f"🎨 显示模式：{mode_map.get(display_mode, display_mode)}")

        custom = db.query("SELECT * FROM custom_rates WHERE group_id=%s ORDER BY rate_name", (group["id"],))
        if custom:
            lines.append("")
            lines.append("🎯 <b>自定义配置</b>")
            for r in custom:
                parts = [f"• {r['rate_name']}"]
                if r.get("fee_rate"): parts.append(f"费率: {r['fee_rate']}%")
                if r.get("exchange_rate"): parts.append(f"汇率: {r['exchange_rate']}")
                lines.append(" ".join(parts))

        await context.bot.send_message(chat_id, "\n".join(lines), parse_mode=ParseMode.HTML)

    async def _show_monthly_bill(self, update, context, group):
        chat_id = update.effective_chat.id
        now = datetime.now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_month = start + timedelta(days=32)
        end = end_month.replace(day=1) - timedelta(seconds=1)

        summary = acc_mgr.get_bill_summary(group["id"], start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"))

        lines = [f"<b>📊 本月总账单</b> ({now.strftime('%Y年%m月')})", "━━━━━━━━━━━━━"]
        if not summary:
            lines.append("暂无记录")
        else:
            totals = {"income": 0, "expense": 0, "distribution": 0}
            for r in summary:
                if r["transaction_type"] in totals:
                    totals[r["transaction_type"]] = float(r["total"] or 0)
            lines.append(f"💰 总入账: {totals['income']:,.2f}")
            lines.append(f"💸 总出账: {totals['expense']:,.2f}")
            lines.append(f"📤 总下发: {totals['distribution']:,.2f}")
            lines.append(f"📊 净收益: {totals['income'] - totals['expense'] - totals['distribution']:,.2f}")

        await context.bot.send_message(chat_id, "\n".join(lines), parse_mode=ParseMode.HTML)

    async def _show_prev_month_bill(self, update, context, group):
        chat_id = update.effective_chat.id
        now = datetime.now()
        prev = now.replace(day=1) - timedelta(days=1)
        start = prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = prev.replace(hour=23, minute=59, second=59)

        summary = acc_mgr.get_bill_summary(group["id"], start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"))

        lines = [f"<b>📊 上月总账单</b> ({start.strftime('%Y年%m月')})", "━━━━━━━━━━━━━"]
        if not summary:
            lines.append("暂无记录")
        else:
            totals = {"income": 0, "expense": 0, "distribution": 0}
            for r in summary:
                if r["transaction_type"] in totals:
                    totals[r["transaction_type"]] = float(r["total"] or 0)
            lines.append(f"💰 总入账: {totals['income']:,.2f}")
            lines.append(f"💸 总出账: {totals['expense']:,.2f}")
            lines.append(f"📤 总下发: {totals['distribution']:,.2f}")
            lines.append(f"📊 净收益: {totals['income'] - totals['expense'] - totals['distribution']:,.2f}")

        await context.bot.send_message(chat_id, "\n".join(lines), parse_mode=ParseMode.HTML)

    async def _show_operator_bill(self, update, context, user, group):
        chat_id = update.effective_chat.id
        rows = db.query(
            "SELECT * FROM transactions WHERE group_id=%s AND operator_id=%s AND is_deleted=0 ORDER BY created_at DESC LIMIT 20",
            (group["id"], user["id"]),
        )
        if not rows:
            await update.message.reply_text("暂无记录")
            return

        icons = {"income": "💰", "expense": "💸", "distribution": "📤"}
        lines = ["<b>👤 我的操作记录</b>", "━━━━━━━━━━━━━"]
        for i, r in enumerate(rows):
            if i >= 10: break
            icon = icons.get(r["transaction_type"], "📊")
            amt = f"{r['amount']:.2f}"
            t = r["created_at"].strftime("%m-%d %H:%M")
            lines.append(f"{i+1}. {icon} {amt} - {t}")
        if len(rows) > 10:
            lines.append(f"\n...还有 {len(rows)-10} 条")
        await context.bot.send_message(chat_id, "\n".join(lines), parse_mode=ParseMode.HTML)

    async def _reset_bill(self, update, context, user, group):
        chat_id = update.effective_chat.id
        ps, pe = self._get_period(group)

        cnt = db.query_one(
            "SELECT COUNT(*) as cnt FROM transactions WHERE group_id=%s AND is_deleted=0 AND created_at BETWEEN %s AND %s",
            (group["id"], ps, pe),
        )["cnt"]
        if cnt == 0:
            await update.message.reply_text("⚠️ 当前周期无数据")
            return

        db.execute(
            "UPDATE transactions SET is_deleted=1 WHERE group_id=%s AND is_deleted=0 AND created_at BETWEEN %s AND %s",
            (group["id"], ps, pe),
        )
        name = self._display_name(user)
        await update.message.reply_text(f"✅ 已重置 {cnt} 条记录\n👤 {name}")

    async def _send_bill(self, update, context, group):
        bill_text = bill_fmt.generate_bill(group["id"])
        await context.bot.send_message(update.effective_chat.id, bill_text, parse_mode=ParseMode.HTML)

    # ===================== 命令处理 =====================

    async def _cmd_start(self, update, context, user, group):
        chat_id = update.effective_chat.id
        if group:
            msg = ("🔧 <b>设置向导</b>\n\n"
                   "1️⃣ 设置费率：<code>设置费率70%</code>\n"
                   "2️⃣ 设置汇率：<code>设置美元汇率6.5</code>\n"
                   "3️⃣ 添加操作人：<code>设置操作人 @用户名</code>\n"
                   "4️⃣ 发送 <code>开始</code> 激活记账\n\n"
                   "💱 USDT价格：lk / lz / lw\n"
                   "💡 每日默认周期：凌晨4点至第二天4点")
        else:
            msg = ("🤖 <b>记账助手</b>\n\n"
                   "💰 +100 / -50 / +100/6.5\n"
                   "📤 下发100 / 下发100u\n"
                   "🔧 入款-100 / 下发-50\n"
                   "📋 显示账单 / 显示完整账单\n"
                   "⚙️ 设置费率X% / 设置美元汇率X\n"
                   "👥 设置操作人 @xxx\n"
                   "🎨 设置为计数模式 / 设置显示模式2\n"
                   "💱 lk / lz / lw\n\n"
                   "📌 群组中使用，请先将机器人拉入群聊！")
        await context.bot.send_message(chat_id, msg, parse_mode=ParseMode.HTML)

    async def _cmd_help(self, update, context):
        chat_id = update.effective_chat.id
        msg = ("📚 <b>命令列表</b>\n━━━━━━━━━━━━━\n\n"
               "💰 <b>记账</b>：+100 / -50 / +100/6.5\n"
               "📤 <b>下发</b>：下发100 / 下发100u\n"
               "🔧 <b>纠错</b>：入款-100 / 下发-50\n"
               "📋 <b>查询</b>：显示账单 / 显示完整账单\n"
               "⚙️ <b>配置</b>：设置费率X% / 设置美元汇率X\n"
               "👥 <b>操作人</b>：设置操作人 @xxx / 显示操作人\n"
               "🎨 <b>模式</b>：设置为计数模式 / 设置显示模式2\n"
               "💱 <b>币价</b>：lk / lz / lw\n"
               "📌 /set 5 / /gd 6.8 / /usdt\n"
               "🔄 撤销 / 开始 / 结束记录")
        await context.bot.send_message(chat_id, msg, parse_mode=ParseMode.HTML)

    async def _cmd_set_fee(self, update, context, user, group, args):
        chat_id = update.effective_chat.id
        if not self._has_permission(user, group):
            await update.message.reply_text("❌ 无权限！")
            return
        try:
            fee = float(args.strip())
            self._set_setting(group["id"], "fee_rate", str(fee))
            await update.message.reply_text(f"✅ 费率已设置为 {fee}%")
        except ValueError:
            await update.message.reply_text("❌ 格式：/set 5")

    async def _cmd_fix_rate(self, update, context, user, group, args):
        chat_id = update.effective_chat.id
        if not self._has_permission(user, group):
            await update.message.reply_text("❌ 无权限！")
            return
        try:
            rate = float(args.strip())
            self._set_setting(group["id"], "exchange_rate", str(rate))
            self._set_setting(group["id"], "rate_source", "fixed")
            await update.message.reply_text(f"✅ 汇率已固定为 {rate}")
        except ValueError:
            await update.message.reply_text("❌ 格式：/gd 6.8")

    async def _cmd_usdt_price(self, update, context):
        chat_id = update.effective_chat.id
        k = price_ck.get_bank_card_price()
        z = price_ck.get_alipay_price()
        w = price_ck.get_wechat_price()

        lines = ["<b>💱 欧易 USDT 实时价格</b>", "━━━━━━━━━━━━━"]
        if k: lines.append(f"💳 银行卡：{k['buy']} / {k['sell']}")
        if z: lines.append(f"💙 支付宝：{z['buy']} / {z['sell']}")
        if w: lines.append(f"💚 微信：{w['buy']} / {w['sell']}")
        lines.append("━━━━━━━━━━━━━")
        lines.append(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await context.bot.send_message(chat_id, "\n".join(lines), parse_mode=ParseMode.HTML)

    # ===================== 辅助方法 =====================

    def _get_period(self, group) -> tuple:
        """获取当前记账周期"""
        ps = self._get_setting(group["id"], "period_start")
        if not ps:
            now = datetime.now()
            today_4am = now.replace(hour=4, minute=0, second=0, microsecond=0)
            if now.hour < 4:
                ps = (today_4am - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                ps = today_4am.strftime("%Y-%m-%d %H:%M:%S")
        pe = (datetime.strptime(ps, "%Y-%m-%d %H:%M:%S") + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        return ps, pe

    def _has_permission(self, user, group) -> bool:
        if user["telegram_id"] in ADMIN_USER_IDS:
            return True
        if user["permission_level"] <= 1:
            return True
        r = db.query_one(
            "SELECT id FROM group_operators WHERE group_id=%s AND user_id=%s",
            (group["id"], user["id"]),
        )
        return bool(r)

    def _is_accounting_enabled(self, group_id) -> bool:
        r = db.query_one("SELECT accounting_status FROM groups WHERE id=%s", (group_id,))
        return r and r["accounting_status"] == 1

    def _get_or_create_user(self, tg_user) -> dict:
        r = db.query_one("SELECT * FROM users WHERE telegram_id=%s", (tg_user.id,))
        if not r:
            uid = db.insert("users", {
                "telegram_id": tg_user.id,
                "username": tg_user.username,
                "first_name": tg_user.first_name,
                "last_name": tg_user.last_name,
                "permission_level": 3,
            })
            r = db.query_one("SELECT * FROM users WHERE id=%s", (uid,))
        else:
            db.execute(
                "UPDATE users SET username=%s, first_name=%s, last_name=%s, updated_at=NOW() WHERE id=%s",
                (tg_user.username, tg_user.first_name, tg_user.last_name, r["id"]),
            )
            r = db.query_one("SELECT * FROM users WHERE id=%s", (r["id"],))
        return r

    def _get_or_create_group(self, chat) -> dict:
        r = db.query_one("SELECT * FROM groups WHERE telegram_group_id=%s", (chat.id,))
        if not r:
            gid = db.insert("groups", {
                "telegram_group_id": chat.id,
                "group_name": chat.title or "",
                "group_type": chat.type,
            })
            r = db.query_one("SELECT * FROM groups WHERE id=%s", (gid,))
        else:
            db.execute(
                "UPDATE groups SET group_name=%s, group_type=%s, updated_at=NOW() WHERE id=%s",
                (chat.title, chat.type, r["id"]),
            )
            r = db.query_one("SELECT * FROM groups WHERE id=%s", (r["id"],))
        return r

    def _get_setting(self, group_id: int, key: str, default=None):
        r = db.query_one(
            "SELECT setting_value FROM group_settings WHERE group_id=%s AND setting_key=%s",
            (group_id, key),
        )
        return r["setting_value"] if r else default

    def _set_setting(self, group_id: int, key: str, value):
        db.execute(
            """INSERT INTO group_settings (group_id, setting_key, setting_value)
               VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE setting_value=%s""",
            (group_id, key, str(value), str(value)),
        )

    def _set_custom_rate(self, group_id: int, name: str, fee_rate, exchange_rate):
        r = db.query_one(
            "SELECT id FROM custom_rates WHERE group_id=%s AND rate_name=%s",
            (group_id, name),
        )
        if r:
            if fee_rate is not None:
                db.execute("UPDATE custom_rates SET fee_rate=%s WHERE id=%s", (fee_rate, r["id"]))
            if exchange_rate is not None:
                db.execute("UPDATE custom_rates SET exchange_rate=%s WHERE id=%s", (exchange_rate, r["id"]))
        else:
            db.insert("custom_rates", {
                "group_id": group_id,
                "rate_name": name,
                "fee_rate": fee_rate,
                "exchange_rate": exchange_rate,
            })

    def _del_custom_rate(self, group_id: int, name: str):
        db.execute("DELETE FROM custom_rates WHERE group_id=%s AND rate_name=%s", (group_id, name))

    async def _add_operator_by_user(self, update, context, group, tg_user):
        target = self._get_or_create_user(tg_user)
        if self._is_operator(group["id"], target["id"]):
            await update.message.reply_text(f"⚠️ {self._display_name(target)} 已经是操作人了")
            return
        db.insert("group_operators", {
            "group_id": group["id"],
            "user_id": target["id"],
            "added_by": None,
        })
        await update.message.reply_text(f"✅ 已将 {self._display_name(target)} 设为操作人")

    def _add_operator_by_username(self, group, username, added_by_user) -> bool:
        target = db.query_one("SELECT * FROM users WHERE username=%s", (username,))
        if not target:
            return False
        if self._is_operator(group["id"], target["id"]):
            return False
        db.insert("group_operators", {
            "group_id": group["id"],
            "user_id": target["id"],
            "added_by": added_by_user["id"],
        })
        return True

    async def _remove_operator(self, update, context, group, username):
        target = db.query_one("SELECT * FROM users WHERE username=%s", (username,))
        if not target:
            await update.message.reply_text(f"❌ 未找到用户 @{username}")
            return
        if not self._is_operator(group["id"], target["id"]):
            await update.message.reply_text(f"⚠️ @{username} 不是操作人")
            return
        db.execute("DELETE FROM group_operators WHERE group_id=%s AND user_id=%s", (group["id"], target["id"]))
        await update.message.reply_text(f"✅ 已将 {self._display_name(target)} 从操作人中移除")

    def _is_operator(self, group_id, user_id):
        return bool(db.query_one(
            "SELECT id FROM group_operators WHERE group_id=%s AND user_id=%s",
            (group_id, user_id),
        ))

    @staticmethod
    def _display_name(user) -> str:
        if user.get("username"):
            return f"@{user['username']}"
        name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        return name or f"User#{user['telegram_id']}"