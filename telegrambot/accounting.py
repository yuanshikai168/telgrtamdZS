"""
记账逻辑模块
"""
import re
from datetime import datetime
from database import Database
from config import DEFAULT_FEE_RATE, DEFAULT_EXCHANGE_RATE

db = Database.get_instance()


class AccountingManager:
    """记账核心逻辑"""

    def parse_command(self, text: str, group_id: int) -> dict:
        """解析记账命令"""
        text = text.strip()
        fee_rate = self._get_setting(group_id, "fee_rate", DEFAULT_FEE_RATE)
        exchange_rate = self._get_setting(group_id, "exchange_rate", DEFAULT_EXCHANGE_RATE)

        # 撤销
        if text == "撤销":
            return {"success": True, "data": {"type": "undo", "action": "undo_last"}}

        # 下发命令
        if text.startswith("下发"):
            return self._parse_distribution(text, group_id, exchange_rate)

        # 基础记账 (+入账, -出账)
        m = re.match(r"^([+\-])(.+)$", text)
        if m:
            sign, amount_part = m.group(1), m.group(2).strip()
            txn_type = "income" if sign == "+" else "expense"
            return self._parse_amount(amount_part, txn_type, group_id, fee_rate, exchange_rate)

        # 分组记账 (张三+10000)
        m = re.match(r"^(.+?)([+\-])(.+)$", text)
        if m:
            category, sign, amount_part = m.group(1).strip(), m.group(2), m.group(3).strip()
            txn_type = "income" if sign == "+" else "expense"
            result = self._parse_amount(amount_part, txn_type, group_id, fee_rate, exchange_rate)
            if result["success"]:
                result["data"]["category"] = category
            return result

        return {"success": False, "error": "无法识别的记账格式"}

    def parse_correction(self, text: str, group_id: int) -> dict:
        """解析纠错命令：入款-XXX, 下发-XXX"""
        text = text.strip()
        exchange_rate = self._get_setting(group_id, "exchange_rate", DEFAULT_EXCHANGE_RATE)

        # 入款纠错
        m = re.match(r"^入款-([\d\.,]+)$", text)
        if m:
            amount = self._parse_num(m.group(1))
            return {
                "success": True,
                "data": {
                    "type": "correction",
                    "sub_type": "income_correction",
                    "amount": -amount,
                    "original_amount": -amount,
                    "fee_rate": 0,
                    "exchange_rate": exchange_rate,
                    "currency": "CNY",
                    "note": "入款修正",
                },
            }

        # 下发纠错
        m = re.match(r"^下发-([\d\.,]+)$", text)
        if m:
            amount = self._parse_num(m.group(1))
            return {
                "success": True,
                "data": {
                    "type": "correction",
                    "sub_type": "distribution_correction",
                    "amount": -amount,
                    "original_amount": -amount,
                    "fee_rate": 0,
                    "exchange_rate": exchange_rate,
                    "currency": "CNY",
                    "note": "下发修正",
                },
            }

        return {"success": False, "error": "无法识别的纠错格式"}

    def _parse_distribution(self, text: str, group_id: int, default_rate: float) -> dict:
        m = re.match(r"^下发([\d\.,]+)(.*)$", text)
        if not m:
            return {"success": False, "error": "下发命令格式错误"}

        amount_str, suffix = m.group(1), m.group(2).strip()
        amount = self._parse_num(amount_str)
        currency = "CNY"
        is_usdt = False
        exchange_rate = default_rate

        if suffix.lower().endswith("u"):
            is_usdt = True
            currency = "USDT"
            realtime_rate = self._get_realtime_rate(group_id)
            if realtime_rate:
                exchange_rate = realtime_rate

        return {
            "success": True,
            "data": {
                "type": "distribution",
                "amount": amount,
                "original_amount": amount,
                "exchange_rate": exchange_rate,
                "currency": currency,
                "is_usdt": is_usdt,
                "fee_rate": 0,
            },
        }

    def _parse_amount(self, amount_part: str, txn_type: str, group_id: int,
                       default_fee: float, default_rate: float) -> dict:
        base = {
            "success": False,
            "error": "",
            "data": {
                "type": txn_type,
                "amount": 0,
                "original_amount": 0,
                "fee_rate": default_fee,
                "exchange_rate": default_rate,
                "currency": "CNY",
                "category": None,
                "note": None,
                "is_usdt": False,
                "custom_rate_name": None,
            },
        }

        # 提取备注
        parts = amount_part.split(" ", 1)
        main_part = parts[0]
        note = parts[1] if len(parts) > 1 else None
        base["data"]["note"] = note

        # 快捷费扣格式 (-1000*105%)
        m = re.match(r"^([\d\.,]+)\*(\d+(?:\.\d+)?)%$", main_part)
        if m:
            amount = self._parse_num(m.group(1))
            fee_percent = float(m.group(2))
            base["data"]["original_amount"] = amount
            base["data"]["amount"] = amount * (fee_percent / 100)
            base["data"]["fee_rate"] = fee_percent - 100
            base["success"] = True
            return base

        # USDT 格式 (7777u)
        m = re.match(r"^([\d\.,]+)u$", main_part, re.IGNORECASE)
        if m:
            usdt_amount = self._parse_num(m.group(1))
            current_rate = self._get_realtime_rate(group_id) or default_rate
            base["data"]["original_amount"] = usdt_amount
            base["data"]["amount"] = usdt_amount * current_rate
            base["data"]["exchange_rate"] = current_rate
            base["data"]["currency"] = "USDT"
            base["data"]["is_usdt"] = True
            base["success"] = True
            return base

        # 指定汇率 (10000/7.8 或 10000/欧元)
        if "/" in main_part:
            rate_parts = main_part.split("/", 1)
            if len(rate_parts) == 2:
                amount = self._parse_num(rate_parts[0])
                rate_part = rate_parts[1].strip()

                # 自定义汇率名称
                custom = self._get_custom_rate(group_id, rate_part)
                if custom:
                    base["data"]["amount"] = amount
                    base["data"]["original_amount"] = amount
                    base["data"]["fee_rate"] = custom.get("fee_rate") or default_fee
                    base["data"]["exchange_rate"] = custom.get("exchange_rate") or default_rate
                    base["data"]["custom_rate_name"] = rate_part
                    base["success"] = True
                    return base

                # 数字汇率
                try:
                    r = float(rate_part)
                    base["data"]["amount"] = amount
                    base["data"]["original_amount"] = amount
                    base["data"]["exchange_rate"] = r
                    base["success"] = True
                    return base
                except ValueError:
                    pass

        # 基础金额
        cleaned = main_part.replace(",", "")
        try:
            amount = float(cleaned)
            base["data"]["amount"] = amount
            base["data"]["original_amount"] = amount
            base["success"] = True
            return base
        except ValueError:
            base["error"] = "无法解析金额"
            return base

    def execute_transaction(self, data: dict, user: dict, group: dict, message_id: int = None) -> int:
        """执行记账交易"""
        try:
            # 撤销
            if data.get("type") == "undo":
                last = db.query_one(
                    "SELECT id FROM transactions WHERE group_id=%s AND operator_id=%s "
                    "AND is_deleted=0 ORDER BY created_at DESC LIMIT 1",
                    (group["id"], user["id"]),
                )
                if not last:
                    raise Exception("没有可撤销的记录")
                db.execute("UPDATE transactions SET is_deleted=1 WHERE id=%s", (last["id"],))
                return last["id"]

            # 普通交易
            txn = {
                "group_id": group["id"],
                "user_id": user["id"],
                "operator_id": user["id"],
                "message_id": message_id,
                "transaction_type": data["type"],
                "amount": data["amount"],
                "original_amount": data.get("original_amount", data["amount"]),
                "fee_rate": data.get("fee_rate", 0),
                "exchange_rate": data.get("exchange_rate", 1),
                "currency": data.get("currency", "CNY"),
                "category": data.get("category"),
                "note": data.get("note"),
                "is_pending": 0,
            }
            return db.insert("transactions", txn)

        except Exception as e:
            import logging
            logging.error(f"交易执行失败: {e}")
            return 0

    # ===== 查询方法 =====

    def get_group_transactions(self, group_id: int, start_date: str, end_date: str,
                                txn_type: str = None, limit: int = 100):
        sql = """SELECT t.*, u.username, u.first_name 
                 FROM transactions t
                 LEFT JOIN users u ON t.user_id = u.id
                 WHERE t.group_id=%s AND t.is_deleted=0
                 AND t.created_at BETWEEN %s AND %s"""
        params = [group_id, start_date, end_date]
        if txn_type:
            sql += " AND t.transaction_type=%s"
            params.append(txn_type)
        sql += " ORDER BY t.created_at DESC"
        if limit:
            sql += f" LIMIT {limit}"
        return db.query(sql, params)

    def get_bill_summary(self, group_id: int, start_date: str, end_date: str):
        return db.query(
            """SELECT transaction_type, COUNT(*) as cnt, SUM(amount) as total
               FROM transactions
               WHERE group_id=%s AND is_deleted=0
               AND created_at BETWEEN %s AND %s
               GROUP BY transaction_type""",
            (group_id, start_date, end_date),
        )

    def get_total_amount(self, group_id: int, txn_type: str,
                         start_date: str, end_date: str):
        r = db.query_one(
            """SELECT COALESCE(SUM(amount), 0) as total FROM transactions
               WHERE group_id=%s AND transaction_type=%s AND is_deleted=0
               AND created_at BETWEEN %s AND %s""",
            (group_id, txn_type, start_date, end_date),
        )
        return float(r["total"]) if r else 0.0

    def get_all_income_records(self, group_id: int, start_date: str, end_date: str):
        return db.query(
            """SELECT original_amount, fee_rate FROM transactions
               WHERE group_id=%s AND transaction_type='income' AND is_deleted=0
               AND created_at BETWEEN %s AND %s""",
            (group_id, start_date, end_date),
        )

    def get_group_users(self, group_id: int):
        return db.query(
            "SELECT u.* FROM users u JOIN group_operators g ON u.id=g.user_id WHERE g.group_id=%s",
            (group_id,),
        )

    # ===== 辅助方法 =====

    def _get_setting(self, group_id: int, key: str, default=None):
        r = db.query_one(
            "SELECT setting_value FROM group_settings WHERE group_id=%s AND setting_key=%s",
            (group_id, key),
        )
        if r:
            val = r["setting_value"]
            if key in ("fee_rate", "exchange_rate"):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return default
            return val
        return default

    def _get_custom_rate(self, group_id: int, rate_name: str):
        return db.query_one(
            "SELECT * FROM custom_rates WHERE group_id=%s AND rate_name=%s",
            (group_id, rate_name),
        )

    def _get_realtime_rate(self, group_id: int):
        source = self._get_setting(group_id, "rate_source")
        if source == "huobi":
            return self._fetch_huobi()
        elif source == "okx":
            return self._fetch_okx()
        return None

    def _fetch_huobi(self):
        try:
            import requests
            r = requests.get("https://api.huobi.pro/market/detail/merged?symbol=usdtcny", timeout=10)
            data = r.json()
            return float(data["tick"]["close"]) if data.get("status") == "ok" else None
        except Exception:
            return None

    def _fetch_okx(self):
        try:
            import requests
            r = requests.get("https://www.okx.com/api/v5/market/ticker?instId=USDT-CNY", timeout=10)
            data = r.json()
            return float(data["data"][0]["last"]) if data.get("data") else None
        except Exception:
            return None

    @staticmethod
    def _parse_num(s: str) -> float:
        return float(s.replace(",", ""))