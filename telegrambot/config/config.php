<?php
/**
 * Telegram记账机器人配置文件
 * 支持环境变量配置 (Railway/Heroku 等云平台)
 */

// 数据库配置 (优先使用环境变量)
define('DB_HOST', getenv('DB_HOST') ?: 'localhost');
define('DB_PORT', getenv('DB_PORT') ?: '3306');
define('DB_NAME', getenv('DB_NAME') ?: getenv('MYSQLDATABASE') ?: 'telegram_accounting_bot');
define('DB_USER', getenv('DB_USER') ?: getenv('MYSQLUSER') ?: 'root');
define('DB_PASS', getenv('DB_PASS') ?: getenv('MYSQLPASSWORD') ?: '');
define('DB_CHARSET', 'utf8mb4');

// Telegram Bot配置
define('BOT_TOKEN', getenv('BOT_TOKEN') ?: 'token');
define('BOT_USERNAME', getenv('BOT_USERNAME') ?: '@your_bot_username');

// API配置
define('TELEGRAM_API_URL', 'https://api.telegram.org/bot' . BOT_TOKEN . '/');

// 默认配置
define('DEFAULT_FEE_RATE', intval(getenv('DEFAULT_FEE_RATE') ?: 10));
define('DEFAULT_EXCHANGE_RATE', floatval(getenv('DEFAULT_EXCHANGE_RATE') ?: 7.2));
define('DEFAULT_TIMEZONE', getenv('DEFAULT_TIMEZONE') ?: 'Asia/Shanghai');

// 权限等级
define('PERMISSION_SUPER_ADMIN', 0);
define('PERMISSION_ADMIN', 1);
define('PERMISSION_OPERATOR', 2);
define('PERMISSION_USER', 3);

// 管理员ID (逗号分隔的环境变量)
$adminIds = getenv('ADMIN_USER_IDS') ?: '';
define('ADMIN_USER_IDS', $adminIds ? array_map('intval', explode(',', $adminIds)) : []);

// Redis配置 (可选)
define('REDIS_HOST', getenv('REDIS_HOST') ?: '127.0.0.1');
define('REDIS_PORT', intval(getenv('REDIS_PORT') ?: 6379));
define('REDIS_PASSWORD', getenv('REDIS_PASSWORD') ?: '');
define('REDIS_DATABASE', intval(getenv('REDIS_DATABASE') ?: 0));

// 实时汇率API配置
define('HUOBI_API_URL', 'https://api.huobi.pro/market/detail/merged?symbol=usdtcny');
define('OKX_API_URL', 'https://www.okx.com/api/v5/market/ticker?instId=USDT-CNY');

// 系统配置
define('DEBUG_MODE', getenv('DEBUG_MODE') === 'true');
define('APP_URL', getenv('APP_URL') ?: 'https://your-domain.com');

// 时区设置
date_default_timezone_set(DEFAULT_TIMEZONE);

// 错误报告
if (DEBUG_MODE) {
    error_reporting(E_ALL);
    ini_set('display_errors', 1);
} else {
    error_reporting(0);
    ini_set('display_errors', 0);
}


