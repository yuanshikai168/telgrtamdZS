FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY telegrambot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY telegrambot/ /app/

# 复制启动脚本
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8080

ENTRYPOINT ["/start.sh"]