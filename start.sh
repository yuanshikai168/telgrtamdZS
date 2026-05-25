#!/bin/bash
set -e

echo "Starting Telegram Bot..."

# 等待 MySQL 就绪
python3 -c "
import pymysql, os, time
host = os.getenv('DB_HOST') or os.getenv('MYSQLHOST') or 'localhost'
user = os.getenv('DB_USER') or os.getenv('MYSQLUSER') or 'root'
password = os.getenv('DB_PASS') or os.getenv('MYSQLPASSWORD') or ''
for i in range(30):
    try:
        conn = pymysql.connect(host=host, user=user, password=password, connect_timeout=3)
        conn.close()
        print('MySQL is ready')
        break
    except Exception:
        print(f'Waiting for MySQL... ({i+1}/30)')
        time.sleep(2)
"

# 启动应用
cd /app
gunicorn main:app --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 2 --worker-class sync --timeout 120