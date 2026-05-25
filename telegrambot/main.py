"""
Telegram 记账机器人 - Flask Webhook 入口
"""
import os
import logging
import sys
import pymysql as _

from flask import Flask, request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import BOT_TOKEN, APP_URL, PORT, DB_HOST, DB_NAME, DB_USER, DB_PASS
from database import Database
from handler import BotHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 创建 Application
application = Application.builder().token(BOT_TOKEN).build()
bot_handler = BotHandler()

# 注册处理器
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handler.handle_message))
application.add_handler(CommandHandler(
    ["start", "set", "gd", "usdt", "help"],
    bot_handler.handle_message,
))


def init_database():
    """初始化数据库：创建数据库和建表"""
    logger.info("正在初始化数据库...")
    db_root = pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASS,
        charset="utf8mb4", connect_timeout=10,
    )
    with db_root.cursor() as cur:
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    db_root.close()

    db = Database.get_instance()
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if os.path.exists(schema_path):
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()
        statements = [s.strip() for s in sql.split(";") if s.strip()
                      and not s.strip().startswith("--")
                      and not s.strip().upper().startswith("CREATE DATABASE")
                      and not s.strip().upper().startswith("USE")]
        for stmt in statements:
            try:
                db.execute(stmt)
            except Exception as e:
                logger.warning(f"SQL 执行警告: {e}")

    logger.info("数据库初始化完成")


@app.route("/webhook", methods=["POST"])
async def webhook():
    """Telegram Webhook 端点"""
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return Response("OK", status=200)
    except Exception as e:
        logger.error(f"Webhook 错误: {e}")
        return Response("Internal Server Error", status=500)


@app.route("/", methods=["GET"])
def index():
    """首页"""
    return f"""
    <h1>Telegram 记账机器人</h1>
    <p>状态：运行中</p>
    <p>Bot: {os.getenv('BOT_USERNAME', '未配置')}</p>
    """


@app.route("/bill_detail", methods=["GET"])
def bill_detail():
    """账单详情页面"""
    from flask import request as req

    token = req.args.get("token")
    group_id = req.args.get("group_id")
    date = req.args.get("date", "")

    if not token or not group_id:
        return "<h3>无效的参数</h3>"
    if not date:
        from datetime import datetime
        date = datetime.now().strftime("%Y-%m-%d")

    import hashlib
    expected = hashlib.md5(f"{group_id}_telegram_bot_2024".encode()).hexdigest()
    if token != expected:
        return "<h3>无效的 Token</h3>"

    db = Database.get_instance()
    s = f"{date} 00:00:00"
    e = f"{date} 23:59:59"

    rows = db.query(
        """SELECT t.*, u.username, u.first_name FROM transactions t
           LEFT JOIN users u ON t.user_id=u.id
           WHERE t.group_id=%s AND t.is_deleted=0
           AND t.created_at BETWEEN %s AND %s
           ORDER BY t.created_at DESC""",
        (int(group_id), s, e),
    )

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>账单详情 - {date}</title>
<style>
body{{font-family:system-ui,sans-serif;padding:20px;background:#f5f5f5}}
.container{{max-width:800px;margin:0 auto;background:#fff;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.1)}}
h2{{margin-top:0}}
table{{width:100%;border-collapse:collapse;margin-top:16px}}
th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #eee}}
th{{background:#f8f9fa;font-weight:600}}
tr:hover{{background:#f8f9fa}}
.income{{color:#27ae60}}
.expense{{color:#e74c3c}}
.distribution{{color:#f39c12}}
.summary{{display:flex;gap:16px;margin:16px 0;flex-wrap:wrap}}
.card{{flex:1;min-width:120px;background:#f8f9fa;border-radius:8px;padding:16px;text-align:center}}
.card .val{{font-size:24px;font-weight:bold;margin-top:4px}}
</style>
</head>
<body>
<div class="container">
<h2>📊 账单详情 - {date}</h2>
<div class="summary">"""

    totals = {}
    for r in rows:
        tp = r["transaction_type"]
        totals[tp] = totals.get(tp, 0) + float(r["amount"])

    colors = {"income": "#27ae60", "expense": "#e74c3c", "distribution": "#f39c12"}
    names = {"income": "入款", "expense": "出款", "distribution": "下发"}
    for tp in ["income", "distribution"]:
        v = totals.get(tp, 0)
        html += f'<div class="card"><div>{names.get(tp, tp)}</div><div class="val" style="color:{colors.get(tp)}">{v:,.2f}</div></div>'

    html += "</div><table><tr><th>#</th><th>时间</th><th>类型</th><th>金额</th><th>费率</th><th>汇率</th><th>备注</th></tr>"

    for i, r in enumerate(rows, 1):
        tp = r["transaction_type"]
        icon_map = {"income": "💰", "expense": "💸", "distribution": "📤", "correction": "🔧"}
        colors_map = {"income": "income", "expense": "expense", "distribution": "distribution"}
        t = str(r["created_at"])[11:16] if hasattr(r["created_at"], "strftime") else ""
        fee = f"{r['fee_rate']}%" if r.get("fee_rate") else "-"
        rate = f"{r['exchange_rate']}" if r.get("exchange_rate") else "-"
        note = r.get("note") or ""
        html += f"""<tr>
<td>{i}</td><td>{t}</td>
<td class="{colors_map.get(tp, '')}">{icon_map.get(tp, '📊')} {tp}</td>
<td><b>{r['amount']:,.2f}</b></td>
<td>{fee}</td><td>{rate}</td><td>{note}</td></tr>"""

    html += "</table></div></body></html>"
    return html


def main():
    init_database()

    if APP_URL:
        # Webhook 模式
        webhook_url = f"{APP_URL.rstrip('/')}/webhook"
        logger.info(f"设置 Webhook: {webhook_url}")
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.bot.set_webhook(webhook_url))
        loop.close()
        app.run(host="0.0.0.0", port=PORT)
    else:
        # Polling 模式（开发用）
        logger.info("使用 Polling 模式")
        application.run_polling()


if __name__ == "__main__":
    main()