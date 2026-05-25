"""
账单格式化模块
"""
from datetime import datetime, timedelta
from database import Database
from accounting import AccountingManager

db = Database.get_instance()
acc_mgr = AccountingManager()


class BillFormatter:
    """账单格式化和显示"""

    def __init__(self):
        self._manager = AccountingManager()

    def generate_bill(self, group_id: int, limit: int = 10) -> str:
        """生成自定义格式账单"""
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) - timedelta(seconds=1)
        s, e = start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")

        fee_rate = self._get_fee_rate(group_id)
        display_mode = self._get_setting(group_id, "display_mode", "1")

        # 入账记录
        income_rows = db.query(
            """SELECT t.*, u.username, u.first_name FROM transactions t
               LEFT JOIN users u ON t.user_id=u.id
               WHERE t.group_id=%s AND t.transaction_type='income' AND t.is_deleted=0
               AND t.created_at BETWEEN %s AND %s ORDER BY t.created_at DESC LIMIT %s""",
            (group_id, s, e, limit),
        )
        income_count = db.query_one(
            "SELECT COUNT(*) as cnt FROM transactions WHERE group_id=%s AND transaction_type='income' AND is_deleted=0 AND created_at BETWEEN %s AND %s",
            (group_id, s, e),
        )["cnt"]

        # 下发记录
        dist_rows = db.query(
            """SELECT t.*, u.username, u.first_name FROM transactions t
               LEFT JOIN users u ON t.user_id=u.id
               WHERE t.group_id=%s AND t.transaction_type='distribution' AND t.is_deleted=0
               AND t.created_at BETWEEN %s AND %s ORDER BY t.created_at DESC LIMIT %s""",
            (group_id, s, e, limit),
        )
        dist_count = db.query_one(
            "SELECT COUNT(*) as cnt FROM transactions WHERE group_id=%s AND transaction_type='distribution' AND is_deleted=0 AND created_at BETWEEN %s AND %s",
            (group_id, s, e),
        )["cnt"]

        total_income = self._manager.get_total_amount(group_id, "income", s, e)
        total_dist = self._manager.get_total_amount(group_id, "distribution", s, e)

        # 应下发金额
        all_income = self._manager.get_all_income_records(group_id, s, e)
        should_dist = sum(r["original_amount"] * (r["fee_rate"] / 100) for r in all_income)
        undistributed = should_dist - total_dist

        # 显示模式控制
        if display_mode == "count":
            return self._format_count_mode(income_rows, income_count, total_income)
        elif display_mode == "2":
            limit = 3
            income_rows = income_rows[:3]
            dist_rows = dist_rows[:3]
        elif display_mode == "3":
            limit = 1
            income_rows = income_rows[:1]
            dist_rows = dist_rows[:1]
        elif display_mode == "4":
            return self._format_total_only(total_income, total_dist, should_dist, undistributed, fee_rate)

        return self._format_full(income_rows, income_count, dist_rows, dist_count,
                                  total_income, total_dist, should_dist, undistributed, fee_rate, group_id)

    def generate_period_bill(self, group_id: int, period_start: str, period_end: str, limit: int = 10) -> str:
        """根据周期生成账单"""
        fee_rate = self._get_fee_rate(group_id)

        income_rows = db.query(
            """SELECT t.*, u.username, u.first_name FROM transactions t
               LEFT JOIN users u ON t.user_id=u.id
               WHERE t.group_id=%s AND t.transaction_type='income' AND t.is_deleted=0
               AND t.created_at BETWEEN %s AND %s ORDER BY t.created_at DESC LIMIT %s""",
            (group_id, period_start, period_end, limit),
        )
        dist_rows = db.query(
            """SELECT t.*, u.username, u.first_name FROM transactions t
               LEFT JOIN users u ON t.user_id=u.id
               WHERE t.group_id=%s AND t.transaction_type='distribution' AND t.is_deleted=0
               AND t.created_at BETWEEN %s AND %s ORDER BY t.created_at DESC LIMIT %s""",
            (group_id, period_start, period_end, limit),
        )

        income_count = db.query_one(
            "SELECT COUNT(*) as cnt FROM transactions WHERE group_id=%s AND transaction_type='income' AND is_deleted=0 AND created_at BETWEEN %s AND %s",
            (group_id, period_start, period_end),
        )["cnt"]
        dist_count = db.query_one(
            "SELECT COUNT(*) as cnt FROM transactions WHERE group_id=%s AND transaction_type='distribution' AND is_deleted=0 AND created_at BETWEEN %s AND %s",
            (group_id, period_start, period_end),
        )["cnt"]

        total_income = self._manager.get_total_amount(group_id, "income", period_start, period_end)
        total_dist = self._manager.get_total_amount(group_id, "distribution", period_start, period_end)

        all_income = self._manager.get_all_income_records(group_id, period_start, period_end)
        should_dist = sum(r["original_amount"] * (r["fee_rate"] / 100) for r in all_income)
        undistributed = should_dist - total_dist

        return self._format_full(income_rows, income_count, dist_rows, dist_count,
                                  total_income, total_dist, should_dist, undistributed, fee_rate, group_id)

    def _format_full(self, income_rows, income_count, dist_rows, dist_count,
                      total_income, total_dist, should_dist, undistributed, fee_rate, group_id) -> str:
        lines = []
        lines.append(f"<b>已入账 ({income_count}笔)</b>")
        if not income_rows:
            lines.append("暂无入账记录")
        else:
            for r in income_rows:
                t = r["created_at"].strftime("%H:%M") if hasattr(r["created_at"], "strftime") else str(r["created_at"])[-8:-3]
                amt = self._fmt(r["original_amount"] or r["amount"])
                rec_fee = r.get("fee_rate", 0) or 0
                fee_amt = (r["original_amount"] or r["amount"]) * (rec_fee / 100)
                links = self._make_link(group_id, r.get("message_id"), amt)
                lines.append(f"{t}  {links} {self._sup(str(int(rec_fee)))} = {self._fmt(fee_amt)}")

        lines.append("")
        lines.append(f"<b>已下发 ({dist_count}笔)</b>")
        if not dist_rows:
            lines.append("暂无下发记录")
        else:
            for r in dist_rows:
                t = r["created_at"].strftime("%H:%M") if hasattr(r["created_at"], "strftime") else str(r["created_at"])[-8:-3]
                amt = self._fmt(r["original_amount"] or r["amount"])
                links = self._make_link(group_id, r.get("message_id"), amt)
                lines.append(f"{t}  {links}")

        lines.append("")
        lines.append(f"总入款额：{int(total_income)}")
        lines.append(f"当前费率：{int(fee_rate)}%")
        lines.append("")
        lines.append(f"应下发：{should_dist:.1f} CNY")
        lines.append(f"已下发：{total_dist:.1f} CNY")
        lines.append(f"未下发：{undistributed:.1f} CNY")

        return "\n".join(lines)

    def _format_count_mode(self, income_rows, income_count, total_income) -> str:
        """计数模式：只显示入款简洁信息"""
        lines = [f"<b>入款记录 ({income_count}笔)</b>"]
        if not income_rows:
            lines.append("暂无记录")
        else:
            for i, r in enumerate(income_rows, 1):
                t = r["created_at"].strftime("%H:%M") if hasattr(r["created_at"], "strftime") else str(r["created_at"])[-8:-3]
                amt = int(r["amount"])
                lines.append(f"{i}. {t}  +{amt}")
        lines.append(f"\n总入款：{int(total_income)}")
        return "\n".join(lines)

    def _format_total_only(self, total_income, total_dist, should_dist, undistributed, fee_rate) -> str:
        lines = [
            "<b>账单汇总</b>",
            f"总入款额：{int(total_income)}",
            f"当前费率：{int(fee_rate)}%",
            f"应下发：{should_dist:.1f} CNY",
            f"已下发：{total_dist:.1f} CNY",
            f"未下发：{undistributed:.1f} CNY",
        ]
        return "\n".join(lines)

    def get_group_token(self, group_id: int) -> str:
        import hashlib
        return hashlib.md5(f"{group_id}_telegram_bot_2024".encode()).hexdigest()

    def get_base_url(self) -> str:
        import os
        return os.getenv("APP_URL", "http://localhost:8080")

    def _make_link(self, group_id: int, message_id: int, text: str) -> str:
        if not message_id:
            return f"<b>{text}</b>"
        num_id = self._get_setting(group_id, "telegram_numeric_id")
        if num_id:
            return f'<a href="https://t.me/c/{num_id}/{message_id}"><b>{text}</b></a>'
        return f"<b>{text}</b>"

    def set_group_telegram_id(self, group_id: int, chat_id: int):
        sid = str(chat_id)
        if sid.startswith("-100"):
            num = sid[4:]
        elif sid.startswith("-"):
            num = sid[1:]
        else:
            num = sid
        db.execute(
            """INSERT INTO group_settings (group_id, setting_key, setting_value)
               VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE setting_value=%s""",
            (group_id, "telegram_numeric_id", num, num),
        )

    def _get_fee_rate(self, group_id: int) -> float:
        r = db.query_one(
            "SELECT setting_value FROM group_settings WHERE group_id=%s AND setting_key='fee_rate'",
            (group_id,),
        )
        return float(r["setting_value"]) if r else 10.0

    def _get_setting(self, group_id: int, key: str, default=None):
        r = db.query_one(
            "SELECT setting_value FROM group_settings WHERE group_id=%s AND setting_key=%s",
            (group_id, key),
        )
        return r["setting_value"] if r else default

    @staticmethod
    def _fmt(x: float) -> str:
        x = float(x)
        if x == int(x):
            return str(int(x))
        return f"{x:.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def _sup(s: str) -> str:
        """转换为上标"""
        mapping = {
            "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
            "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
            ".": ".",
        }
        return "".join(mapping.get(c, c) for c in s)