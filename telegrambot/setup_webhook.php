<?php
/**
 * Webhook设置脚本
 */

require_once 'config/config.php';
require_once 'classes/TelegramBot.php';

// 检查是否通过命令行运行
$isCli = php_sapi_name() === 'cli';

if (!$isCli) {
    // Web界面
    ?>
    <!DOCTYPE html>
    <html>
    <head>
        <title>Telegram Bot Webhook 设置</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            .success { color: green; }
            .error { color: red; }
            .info { color: blue; }
            input[type="text"] { width: 100%; padding: 10px; margin: 10px 0; }
            button { padding: 10px 20px; background: #007cba; color: white; border: none; cursor: pointer; }
            button:hover { background: #005a87; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Telegram Bot Webhook 设置</h1>
            
            <?php
            if ($_SERVER['REQUEST_METHOD'] === 'POST') {
                $action = $_POST['action'] ?? '';
                $webhookUrl = $_POST['webhook_url'] ?? '';
                
                try {
                    $bot = new TelegramBot();
                    
                    if ($action === 'set' && !empty($webhookUrl)) {
                        $result = $bot->setWebhook($webhookUrl);
                        if ($result) {
                            echo '<p class="success">✅ Webhook设置成功！</p>';
                            echo '<p class="info">URL: ' . htmlspecialchars($webhookUrl) . '</p>';
                        } else {
                            echo '<p class="error">❌ Webhook设置失败！</p>';
                        }
                    } elseif ($action === 'delete') {
                        $result = $bot->deleteWebhook();
                        if ($result) {
                            echo '<p class="success">✅ Webhook删除成功！</p>';
                        } else {
                            echo '<p class="error">❌ Webhook删除失败！</p>';
                        }
                    }
                } catch (Exception $e) {
                    echo '<p class="error">❌ 错误: ' . htmlspecialchars($e->getMessage()) . '</p>';
                }
            }
            ?>
            
            <h2>设置 Webhook</h2>
            <form method="post">
                <input type="hidden" name="action" value="set">
                <label>Webhook URL:</label>
                <input type="text" name="webhook_url" placeholder="https://yourdomain.com/webhook.php" required>
                <br>
                <button type="submit">设置 Webhook</button>
            </form>
            
            <h2>删除 Webhook</h2>
            <form method="post">
                <input type="hidden" name="action" value="delete">
                <button type="submit" onclick="return confirm('确定要删除Webhook吗？')">删除 Webhook</button>
            </form>
            
            <h2>说明</h2>
            <ul>
                <li>Webhook URL必须是HTTPS地址</li>
                <li>确保webhook.php文件可以正常访问</li>
                <li>建议使用SSL证书保护您的服务器</li>
                <li>设置完成后，机器人将通过Webhook接收消息</li>
            </ul>
            
            <h2>测试</h2>
            <p>设置完成后，向您的机器人发送 /start 消息测试是否正常工作。</p>
        </div>
    </body>
    </html>
    <?php
    exit;
}

// 命令行模式
echo "🤖 Telegram Bot Webhook 设置\n";
echo "============================\n\n";

if (BOT_TOKEN === 'YOUR_BOT_TOKEN_HERE') {
    die("❌ 请先在 config/config.php 中配置您的 Bot Token\n");
}

// 获取命令行参数
$options = getopt("", ["set:", "delete", "help"]);

if (isset($options['help']) || empty($options)) {
    echo "用法:\n";
    echo "  php setup_webhook.php --set=https://yourdomain.com/webhook.php\n";
    echo "  php setup_webhook.php --delete\n";
    echo "  php setup_webhook.php --help\n\n";
    exit;
}

try {
    $bot = new TelegramBot();
    
    if (isset($options['set'])) {
        $webhookUrl = $options['set'];
        echo "🔗 设置 Webhook: {$webhookUrl}\n";
        
        $result = $bot->setWebhook($webhookUrl);
        if ($result) {
            echo "✅ Webhook 设置成功！\n";
        } else {
            echo "❌ Webhook 设置失败！\n";
        }
    } elseif (isset($options['delete'])) {
        echo "🗑️  删除 Webhook...\n";
        
        $result = $bot->deleteWebhook();
        if ($result) {
            echo "✅ Webhook 删除成功！\n";
        } else {
            echo "❌ Webhook 删除失败！\n";
        }
    }
    
} catch (Exception $e) {
    echo "❌ 错误: " . $e->getMessage() . "\n";
}
