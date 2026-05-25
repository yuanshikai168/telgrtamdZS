"""
配置文件 - 从环境变量读取，兼容 Railway 等云平台
"""
import os

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "@your_bot")

# 数据库
DB_HOST = os.getenv("DB_HOST") or os.getenv("MYSQLHOST") or "localhost"
DB_PORT = int(os.getenv("DB_PORT") or os.getenv("MYSQLPORT") or 3306)
DB_NAME = os.getenv("DB_NAME") or os.getenv("MYSQLDATABASE") or "telegram_accounting_bot"
DB_USER = os.getenv("DB_USER") or os.getenv("MYSQLUSER") or "root"
DB_PASS = os.getenv("DB_PASS") or os.getenv("MYSQLPASSWORD") or ""

# 默认配置
DEFAULT_FEE_RATE = float(os.getenv("DEFAULT_FEE_RATE", 10))
DEFAULT_EXCHANGE_RATE = float(os.getenv("DEFAULT_EXCHANGE_RATE", 7.2))
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Shanghai")

# 管理员 ID (逗号分隔)
_admin_ids = os.getenv("ADMIN_USER_IDS", "")
ADMIN_USER_IDS = [int(x) for x in _admin_ids.split(",") if x.strip()] if _admin_ids else []

# 应用地址
APP_URL = os.getenv("APP_URL", "")

# 调试模式
DEBUG = os.getenv("DEBUG_MODE", "false").lower() == "true"

# Webhook 端口
PORT = int(os.getenv("PORT", 8080))