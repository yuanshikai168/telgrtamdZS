<?php
/**
 * 消息处理类 - 处理所有Telegram消息和命令
 */
class MessageHandler {
    private $bot;
    private $userManager;
    private $groupManager;
    private $accountingManager;
    private $billFormatter;
    private $db;
    
    public function __construct() {
        $this->bot = new TelegramBot();
        $this->userManager = new UserManager();
        $this->groupManager = new GroupManager();
        $this->accountingManager = new AccountingManager();
        $this->billFormatter = new BillFormatter();
        $this->db = Database::getInstance();
    }
    
    /**
     * 处理Telegram更新
     */
    public function handleUpdate($update) {
        // 处理普通消息
        if (isset($update['message'])) {
            $this->handleMessage($update['message']);
        }
        
        // 处理回调查询（内联键盘按钮）
        if (isset($update['callback_query'])) {
            $this->handleCallbackQuery($update['callback_query']);
        }
        
        // 处理内联查询
        if (isset($update['inline_query'])) {
            $this->handleInlineQuery($update['inline_query']);
        }
    }
    
    /**
     * 处理普通消息
     */
    private function handleMessage($message) {
        $chatId = $message['chat']['id'];
        $userId = $message['from']['id'];
        $text = $message['text'] ?? '';
        $messageId = $message['message_id'];
        
        // 获取或创建用户
        $user = $this->userManager->getOrCreateUser($message['from']);
        
        // 如果是群组消息，获取或创建群组
        $group = null;
        if ($message['chat']['type'] !== 'private') {
            $group = $this->groupManager->getOrCreateGroup($message['chat']);
            
            // 检查是否是机器人被添加到群组
            if (isset($message['new_chat_members'])) {
                foreach ($message['new_chat_members'] as $newMember) {
                    if ($newMember['id'] == $this->bot->getBotId()) {
                        $this->sendGroupJoinMessage($chatId, $message['chat']);
                        // 机器人刚进群，记账功能默认关闭，需要激活
                        $this->groupManager->setSetting($group['id'], 'accounting_enabled', 0);
                        $this->groupManager->setSetting($group['id'], 'setup_completed', 0);
                        break;
                    }
                }
            }
            
            // 检查记账是否开启
            if (!$this->groupManager->isAccountingEnabled($group['id'])) {
                // 只处理/start命令
                if ($text !== '/start') {
                    // 发送激活提示
                    $this->sendActivationPrompt($chatId, $group);
                    return;
                }
            }
        }
        
        // 处理命令
        if (strpos($text, '/') === 0) {
            $this->handleCommand($text, $chatId, $user, $group, $messageId);
        } else {
            $this->handleTextMessage($text, $chatId, $user, $group, $messageId);
        }
    }
    
    /**
     * 处理命令
     */
    private function handleCommand($text, $chatId, $user, $group, $messageId) {
        $parts = explode(' ', $text, 2);
        $command = strtolower($parts[0]);
        $args = isset($parts[1]) ? $parts[1] : '';
        
        switch ($command) {
            case '/start':
                if ($group) {
                    $this->handleGroupStartCommand($chatId, $user, $group);
                } else {
                    $this->handleStartCommand($chatId, $user);
                }
                break;
                
            case '/help':
                $this->handleHelpCommand($chatId);
                break;
                
            case '/我':
            case '/账单':
                if ($group) {
                    $this->showUserBill($chatId, $user, $group);
                }
                break;
                
            case '/p':
                // 账单寄存命令 /P+2000 或 /P-1000
                if ($group && $args) {
                    $this->handlePendingTransaction($chatId, $user, $group, $args, $messageId);
                }
                break;
                
            default:
                // 检查是否是自定义命令
                $this->handleCustomCommand($command, $chatId, $user, $group);
        }
    }
    
    /**
     * 处理文本消息
     */
    private function handleTextMessage($text, $chatId, $user, $group, $messageId) {
        $text = trim($text);
        
        // 检查是否是记账命令
        if ($this->isAccountingCommand($text)) {
            if ($group) {
                $this->handleAccountingCommand($text, $chatId, $user, $group, $messageId);
            } else {
                $this->bot->sendMessage($chatId, '记账功能只能在群组中使用！');
            }
            return;
        }
        
        // 检查是否是配置命令
        if ($this->isConfigCommand($text)) {
            $this->handleConfigCommand($text, $chatId, $user, $group);
            return;
        }
        
        // 检查是否是操作员管理命令
        if ($this->isOperatorCommand($text)) {
            $this->handleOperatorCommand($text, $chatId, $user, $group);
            return;
        }
        
        // 检查是否是查询命令
        if ($this->isQueryCommand($text)) {
            $this->handleQueryCommand($text, $chatId, $user, $group);
            return;
        }
        
        // 检查关键词回复
        $this->checkKeywordReply($text, $chatId, $group);
    }
    
    /**
     * 处理开始命令
     */
    private function handleStartCommand($chatId, $user) {
        $welcomeText = "🤖 欢迎使用记账助手机器人！\n\n";
        $welcomeText .= "📋 <b>主要功能：</b>\n";
        $welcomeText .= "• 记账入账：+10000\n";
        $welcomeText .= "• 代付减账：-10000\n";
        $welcomeText .= "• 汇率记账：+10000/7.8\n";
        $welcomeText .= "• USDT记账：+7777u\n";
        $welcomeText .= "• 查看账单：账单 或 /账单\n";
        $welcomeText .= "• 下发回分：下发5000\n\n";
        $welcomeText .= "💡 发送 /help 查看完整功能列表\n";
        $welcomeText .= "⚙️ 发送 \"配置\" 查看当前费率汇率设置";
        
        $this->bot->sendMessage($chatId, $welcomeText);
    }
    
    /**
     * 处理帮助命令
     */
    private function handleHelpCommand($chatId) {
        $helpText = "📚 <b>记账助手操作说明</b>\n\n";
        $helpText .= "1️⃣ <b>基本记账操作：</b>\n";
        $helpText .= "• +10000 - 记账入账\n";
        $helpText .= "• -10000 - 代付减账\n";
        $helpText .= "• +10000/7.8 - 指定汇率入账\n";
        $helpText .= "• +7777u - USDT记账（自动计算费汇率）\n\n";
        
        $helpText .= "2️⃣ <b>配置管理：</b>\n";
        $helpText .= "• 设置费率10 - 配置费率\n";
        $helpText .= "• 设置汇率8 - 配置汇率\n";
        $helpText .= "• 设置火币汇率 - 使用火币实时汇率\n";
        $helpText .= "• 设置欧易汇率 - 使用欧易实时汇率\n\n";
        
        $helpText .= "3️⃣ <b>操作员管理：</b>\n";
        $helpText .= "• @username 添加操作员\n";
        $helpText .= "• @username 删除操作员\n";
        $helpText .= "• 显示操作员 - 查看所有操作员\n\n";
        
        $helpText .= "4️⃣ <b>账单管理：</b>\n";
        $helpText .= "• 账单 - 查看当前账单\n";
        $helpText .= "• 总账单 - 查看本月总账\n";
        $helpText .= "• 重置 - 清空当前账单\n";
        $helpText .= "• 撤销 - 撤销上一步操作\n\n";
        
        $helpText .= "💡 更多高级功能请查看完整文档";
        
        $this->bot->sendMessage($chatId, $helpText);
    }
    
    /**
     * 检查是否是记账命令
     */
    private function isAccountingCommand($text) {
        // +入账, -出账, 下发等
        return preg_match('/^[\+\-][\d\.,]+/', $text) || 
               strpos($text, '下发') === 0 ||
               strpos($text, '撤销') === 0;
    }
    
    /**
     * 检查是否是配置命令
     */
    private function isConfigCommand($text) {
        return strpos($text, '设置') === 0 || 
               $text === '配置' || 
               $text === '费率' ||
               strpos($text, '删除') === 0;
    }
    
    /**
     * 检查是否是操作员管理命令
     */
    private function isOperatorCommand($text) {
        return strpos($text, '添加操作员') !== false ||
               strpos($text, '删除操作员') !== false ||
               $text === '设置所有人操作员' ||
               $text === '删除所有人操作员' ||
               $text === '开始记账' ||
               $text === '关闭记账';
    }
    
    /**
     * 检查是否是查询命令
     */
    private function isQueryCommand($text) {
        return $text === '账单' || 
               $text === '总账单' || 
               $text === '上个月总账单' ||
               $text === '显示操作员' ||
               $text === '重置' ||
               $text === '清零' ||
               $text === '清空' ||
               $text === '删除账单' ||
               $text === '结束账单' ||
               strpos($text, '账单') !== false;
    }
    
    /**
     * 检查是否是激活命令
     */
    private function isActivationCommand($text) {
        return $text === '开始记账' || 
               $text === '激活记账' ||
               $text === '启用记账' ||
               $text === '开始' ||
               $text === '激活';
    }
    
    /**
     * 检查是否是管理命令
     */
    private function isManagementCommand($text) {
        return strpos($text, '/') === 0 || 
               $text === '开始记账' || 
               $text === '关闭记账' ||
               $text === '开始' ||
               strpos($text, '设置') === 0;
    }
    
    /**
     * 处理记账命令
     */
    private function handleAccountingCommand($text, $chatId, $user, $group, $messageId) {
        // 检查用户权限
        if (!$this->hasOperatorPermission($user, $group)) {
            $this->bot->sendMessage($chatId, '❌ 您没有记账权限，请联系管理员添加您为操作员！');
            return;
        }
        
        // 解析记账命令
        $result = $this->accountingManager->parseAccountingCommand($text, $group['id']);
        
        if (!$result['success']) {
            $this->bot->sendMessage($chatId, '❌ ' . $result['error']);
            return;
        }
        
        // 执行记账操作
        $transactionId = $this->accountingManager->executeTransaction($result['data'], $user, $group, $messageId);
        
        if ($transactionId) {
            // 只发送更新的账单，不发送操作确认消息
            $this->billFormatter->checkAndSendBill($group['id'], $chatId, $this->bot);
        } else {
            $this->bot->sendMessage($chatId, '❌ 记账操作失败，请稍后重试！');
        }
    }
    
    /**
     * 检查操作员权限
     */
    private function hasOperatorPermission($user, $group) {
        // 超级管理员和管理员始终有权限
        if ($this->userManager->isAdmin($user['id'])) {
            return true;
        }
        
        // 检查是否是群组操作员
        return $this->groupManager->isOperator($group['id'], $user['id']);
    }
    
    
    /**
     * 处理回调查询
     */
    private function handleCallbackQuery($callbackQuery) {
        // 处理内联键盘按钮点击
    }
    
    /**
     * 处理内联查询
     */
    private function handleInlineQuery($inlineQuery) {
        // 处理内联查询
    }
    
    /**
     * 显示用户账单
     */
    private function showUserBill($chatId, $user, $group) {
        try {
            // 获取今日账单
            $startDate = date('Y-m-d 00:00:00');
            $endDate = date('Y-m-d 23:59:59');
            
            $transactions = $this->accountingManager->getGroupBill($group['id'], $startDate, $endDate);
            $summary = $this->accountingManager->getBillSummary($group['id'], $startDate, $endDate);
            
            $response = "📊 <b>今日账单</b> (" . date('Y-m-d') . ")\n";
            $response .= "━━━━━━━━━━━━━━━━━━━━━━\n\n";
            
            if (empty($transactions)) {
                $response .= "📝 今日暂无交易记录";
                $this->bot->sendMessage($chatId, $response);
                return;
            }
            
            // 显示统计信息
            $totalIncome = 0;
            $totalExpense = 0;
            $totalDistribution = 0;
            
            foreach ($summary as $item) {
                switch ($item['transaction_type']) {
                    case 'income':
                        $totalIncome = $item['total_amount'];
                        break;
                    case 'expense':
                        $totalExpense = $item['total_amount'];
                        break;
                    case 'distribution':
                        $totalDistribution = $item['total_amount'];
                        break;
                }
            }
            
            $response .= "💰 总入账: " . number_format($totalIncome, 2) . " CNY\n";
            $response .= "💸 总出账: " . number_format($totalExpense, 2) . " CNY\n";
            $response .= "📤 总下发: " . number_format($totalDistribution, 2) . " CNY\n";
            $response .= "📊 净收益: " . number_format($totalIncome - $totalExpense - $totalDistribution, 2) . " CNY\n\n";
            
            // 显示最近交易记录
            $response .= "📋 <b>最近交易记录</b>\n";
            $response .= "━━━━━━━━━━━━━━━━━━━━━━\n";
            
            $count = 0;
            foreach (array_slice($transactions, 0, 10) as $transaction) {
                $count++;
                $typeIcon = [
                    'income' => '💰',
                    'expense' => '💸',
                    'distribution' => '📤'
                ][$transaction['transaction_type']] ?? '📊';
                
                $amount = number_format($transaction['amount'], 2);
                $time = date('H:i', strtotime($transaction['created_at']));
                
                $response .= "{$count}. {$typeIcon} {$amount} CNY";
                
                if ($transaction['category']) {
                    $response .= " ({$transaction['category']})";
                }
                
                $response .= " - {$time}\n";
            }
            
            if (count($transactions) > 10) {
                $response .= "\n... 还有 " . (count($transactions) - 10) . " 条记录";
            }
            
            $this->bot->sendMessage($chatId, $response);
            
        } catch (Exception $e) {
            $this->bot->sendMessage($chatId, '❌ 获取账单失败：' . $e->getMessage());
        }
    }
    
    /**
     * 处理寄存交易
     */
    private function handlePendingTransaction($chatId, $user, $group, $args, $messageId) {
        // 实现寄存交易逻辑
    }
    
    /**
     * 处理自定义命令
     */
    private function handleCustomCommand($command, $chatId, $user, $group) {
        // 检查自定义命令
    }
    
    /**
     * 处理配置命令
     */
    private function handleConfigCommand($text, $chatId, $user, $group) {
        // 检查权限（操作员以上才能配置）
        if (!$this->hasOperatorPermission($user, $group)) {
            $this->bot->sendMessage($chatId, '❌ 您没有配置权限！');
            return;
        }
        
        $text = trim($text);
        
        try {
            // 查看配置
            if ($text === '配置' || $text === '费率') {
                $this->showCurrentConfig($chatId, $group);
                return;
            }
            
            // 设置费率
            if (preg_match('/^设置费率([\d\.\-]+)$/', $text, $matches)) {
                $feeRate = floatval($matches[1]);
                $this->groupManager->setSetting($group['id'], 'fee_rate', $feeRate);
                $this->bot->sendMessage($chatId, "✅ 费率已设置为 {$feeRate}%");
                return;
            }
            
            // 设置汇率
            if (preg_match('/^设置汇率([\d\.]+)$/', $text, $matches)) {
                $exchangeRate = floatval($matches[1]);
                $this->groupManager->setSetting($group['id'], 'exchange_rate', $exchangeRate);
                $this->bot->sendMessage($chatId, "✅ 汇率已设置为 {$exchangeRate}");
                return;
            }
            
            // 设置实时汇率
            if ($text === '设置火币汇率') {
                $this->groupManager->setSetting($group['id'], 'rate_source', 'huobi');
                $this->bot->sendMessage($chatId, "✅ 已设置使用火币实时汇率");
                return;
            }
            
            if ($text === '设置欧易汇率') {
                $this->groupManager->setSetting($group['id'], 'rate_source', 'okx');
                $this->bot->sendMessage($chatId, "✅ 已设置使用欧易实时汇率");
                return;
            }
            
            // 自定义汇率配置
            if (preg_match('/^设置(.+)费率([\d\.\-]+)$/', $text, $matches)) {
                $rateName = trim($matches[1]);
                $feeRate = floatval($matches[2]);
                $this->setCustomRate($group['id'], $rateName, $feeRate, null);
                $this->bot->sendMessage($chatId, "✅ {$rateName}费率已设置为 {$feeRate}%");
                return;
            }
            
            if (preg_match('/^设置(.+)汇率([\d\.]+)$/', $text, $matches)) {
                $rateName = trim($matches[1]);
                $exchangeRate = floatval($matches[2]);
                $this->setCustomRate($group['id'], $rateName, null, $exchangeRate);
                $this->bot->sendMessage($chatId, "✅ {$rateName}汇率已设置为 {$exchangeRate}");
                return;
            }
            
            // 删除配置
            if (preg_match('/^删除(.+)配置$/', $text, $matches)) {
                $rateName = trim($matches[1]);
                $this->deleteCustomRate($group['id'], $rateName);
                $this->bot->sendMessage($chatId, "✅ 已删除{$rateName}配置");
                return;
            }
            
            if ($text === '删除配置') {
                $this->deleteAllCustomRates($group['id']);
                $this->bot->sendMessage($chatId, "✅ 已清空所有自定义配置");
                return;
            }
            
            $this->bot->sendMessage($chatId, '❌ 无法识别的配置命令');
            
        } catch (Exception $e) {
            $this->bot->sendMessage($chatId, '❌ 配置失败：' . $e->getMessage());
        }
    }
    
    /**
     * 处理操作员管理命令
     */
    private function handleOperatorCommand($text, $chatId, $user, $group) {
        // 检查管理员权限
        if (!$this->userManager->isAdmin($user['id']) && !$this->hasOperatorPermission($user, $group)) {
            $this->bot->sendMessage($chatId, '❌ 您没有管理权限！');
            return;
        }
        
        $text = trim($text);
        
        try {
            // 添加操作员 (@username 添加操作员)
            if (preg_match('/^@(\w+)\s+添加操作员$/', $text, $matches)) {
                $username = $matches[1];
                $this->addOperatorByUsername($chatId, $group, $username, $user);
                return;
            }
            
            // 删除操作员 (@username 删除操作员)
            if (preg_match('/^@(\w+)\s+删除操作员$/', $text, $matches)) {
                $username = $matches[1];
                $this->removeOperatorByUsername($chatId, $group, $username);
                return;
            }
            
            // 设置所有人为操作员
            if ($text === '设置所有人操作员') {
                // 这个功能需要获取群成员列表，暂时提示用户手动添加
                $this->bot->sendMessage($chatId, '⚠️ 此功能需要机器人有获取群成员权限。请手动添加操作员或联系开发者。');
                return;
            }
            
            // 删除所有操作员
            if ($text === '删除所有人操作员') {
                $this->removeAllOperators($chatId, $group);
                return;
            }
            
            // 开始记账
            if ($text === '开始记账' || $text === '开始' || $text === '激活记账' || $text === '激活' || $text === '启用记账') {
                $this->groupManager->setAccountingStatus($group['id'], true);
                
                // 设置群组数字ID用于消息链接
                $this->billFormatter->setGroupTelegramId($group['id'], $chatId);
                
                $activationMessage = "✅ <b>记账功能已激活！</b>\n\n";
                $activationMessage .= "📊 <b>群组信息：</b>\n";
                $activationMessage .= "群组ID：{$chatId}\n";
                $activationMessage .= "状态：已激活\n\n";
                $activationMessage .= "💡 <b>现在可以使用：</b>\n";
                $activationMessage .= "• 记账：+100, -50, 下发等\n";
                $activationMessage .= "• 查看账单：账单, 总账单\n";
                $activationMessage .= "• 管理操作员：@用户名 添加操作员\n";
                $activationMessage .= "• 配置费率：设置费率70\n\n";
                $activationMessage .= "🎉 机器人已准备就绪，开始记账吧！";
                
                $this->bot->sendMessage($chatId, $activationMessage);
                return;
            }
            
            // 完成设置
            if ($text === '完成设置') {
                $this->completeSetup($chatId, $user, $group);
                return;
            }
            
            // 关闭记账
            if ($text === '关闭记账') {
                $this->groupManager->setAccountingStatus($group['id'], false);
                $this->bot->sendMessage($chatId, '✅ 记账功能已关闭');
                return;
            }
            
            $this->bot->sendMessage($chatId, '❌ 无法识别的操作员管理命令');
            
        } catch (Exception $e) {
            $this->bot->sendMessage($chatId, '❌ 操作失败：' . $e->getMessage());
        }
    }
    
    /**
     * 处理查询命令
     */
    private function handleQueryCommand($text, $chatId, $user, $group) {
        $text = trim($text);
        
        try {
            // 显示操作员
            if ($text === '显示操作员') {
                $this->showOperators($chatId, $group);
                return;
            }
            
            // 查看账单
            if ($text === '账单') {
                $customBill = $this->billFormatter->generateCustomBill($group['id']);
                
                // 生成内联键盘（支持多按钮）
                require_once 'classes/ButtonManager.php';
                $buttonManager = new ButtonManager();
                $keyboard = $buttonManager->generateInlineKeyboard($group['id']);
                
                $this->bot->sendMessage($chatId, $customBill, $keyboard);
                return;
            }
            
            // 总账单
            if ($text === '总账单' || $text === '本月总账') {
                $this->showMonthlyBill($chatId, $group);
                return;
            }
            
            // 上月总账单
            if ($text === '上个月总账单' || $text === '上月总账') {
                $this->showPreviousMonthBill($chatId, $group);
                return;
            }
            
            // 指定用户账单查询（张三 账单）
            if (preg_match('/^(.+)\s+账单$/', $text, $matches)) {
                $targetName = trim($matches[1]);
                $this->showUserBillByName($chatId, $group, $targetName);
                return;
            }
            
            // 操作员查看自己的账单
            if ($text === '我的账单') {
                if ($this->hasOperatorPermission($user, $group)) {
                    $this->showOperatorBill($chatId, $user, $group);
                } else {
                    $this->bot->sendMessage($chatId, '❌ 只有操作员才能使用此功能');
                }
                return;
            }
            
            // 重置账单
            if ($text === '重置' || $text === '清零' || $text === '清空' || $text === '删除账单' || $text === '结束账单') {
                if ($this->hasOperatorPermission($user, $group)) {
                    $this->resetBill($chatId, $user, $group);
                } else {
                    $this->bot->sendMessage($chatId, '❌ 您没有重置权限！');
                }
                return;
            }
            
            $this->bot->sendMessage($chatId, '❌ 无法识别的查询命令');
            
        } catch (Exception $e) {
            $this->bot->sendMessage($chatId, '❌ 查询失败：' . $e->getMessage());
        }
    }
    
    /**
     * 检查关键词回复
     */
    private function checkKeywordReply($text, $chatId, $group) {
        // 实现关键词自动回复
    }
    
    /**
     * 显示当前配置
     */
    private function showCurrentConfig($chatId, $group) {
        $feeRate = $this->groupManager->getSetting($group['id'], 'fee_rate', DEFAULT_FEE_RATE);
        $exchangeRate = $this->groupManager->getSetting($group['id'], 'exchange_rate', DEFAULT_EXCHANGE_RATE);
        $rateSource = $this->groupManager->getSetting($group['id'], 'rate_source', 'manual');
        
        $response = "⚙️ <b>当前配置</b>\n";
        $response .= "━━━━━━━━━━━━━━━━━━━━━━\n\n";
        $response .= "📊 费率: {$feeRate}%\n";
        $response .= "💱 汇率: {$exchangeRate}\n";
        
        $rateSourceText = [
            'manual' => '手动设置',
            'huobi' => '火币实时汇率',
            'okx' => '欧易实时汇率'
        ][$rateSource] ?? '未知';
        
        $response .= "🔄 汇率来源: {$rateSourceText}\n\n";
        
        // 显示自定义配置
        $customRates = $this->getCustomRates($group['id']);
        if (!empty($customRates)) {
            $response .= "🎯 <b>自定义配置</b>\n";
            $response .= "━━━━━━━━━━━━━━━━━━━━━━\n";
            
            foreach ($customRates as $rate) {
                $response .= "• {$rate['rate_name']}";
                if ($rate['fee_rate'] !== null) {
                    $response .= " 费率: {$rate['fee_rate']}%";
                }
                if ($rate['exchange_rate'] !== null) {
                    $response .= " 汇率: {$rate['exchange_rate']}";
                }
                $response .= "\n";
            }
        }
        
        $this->bot->sendMessage($chatId, $response);
    }
    
    /**
     * 设置自定义汇率
     */
    private function setCustomRate($groupId, $rateName, $feeRate, $exchangeRate) {
        // 先尝试更新现有记录
        $existing = $this->db->fetch(
            "SELECT * FROM custom_rates WHERE group_id = :group_id AND rate_name = :rate_name",
            ['group_id' => $groupId, 'rate_name' => $rateName]
        );
        
        if ($existing) {
            $updateData = [];
            if ($feeRate !== null) {
                $updateData['fee_rate'] = $feeRate;
            }
            if ($exchangeRate !== null) {
                $updateData['exchange_rate'] = $exchangeRate;
            }
            
            if (!empty($updateData)) {
                $this->db->update(
                    'custom_rates',
                    $updateData,
                    'id = :id',
                    ['id' => $existing['id']]
                );
            }
        } else {
            // 创建新记录
            $this->db->insert('custom_rates', [
                'group_id' => $groupId,
                'rate_name' => $rateName,
                'fee_rate' => $feeRate,
                'exchange_rate' => $exchangeRate
            ]);
        }
    }
    
    /**
     * 获取自定义汇率
     */
    private function getCustomRates($groupId) {
        return $this->db->fetchAll(
            "SELECT * FROM custom_rates WHERE group_id = :group_id ORDER BY rate_name",
            ['group_id' => $groupId]
        );
    }
    
    /**
     * 删除自定义汇率
     */
    private function deleteCustomRate($groupId, $rateName) {
        return $this->db->delete(
            'custom_rates',
            'group_id = :group_id AND rate_name = :rate_name',
            ['group_id' => $groupId, 'rate_name' => $rateName]
        );
    }
    
    /**
     * 删除所有自定义汇率
     */
    private function deleteAllCustomRates($groupId) {
        return $this->db->delete(
            'custom_rates',
            'group_id = :group_id',
            ['group_id' => $groupId]
        );
    }
    
    /**
     * 通过用户名添加操作员
     */
    private function addOperatorByUsername($chatId, $group, $username, $addedBy) {
        // 查找用户
        $targetUser = $this->db->fetch(
            "SELECT * FROM users WHERE username = :username",
            ['username' => $username]
        );
        
        if (!$targetUser) {
            $this->bot->sendMessage($chatId, "❌ 未找到用户 @{$username}，请确保该用户已与机器人互动过");
            return;
        }
        
        // 检查是否已经是操作员
        if ($this->groupManager->isOperator($group['id'], $targetUser['id'])) {
            $this->bot->sendMessage($chatId, "⚠️ @{$username} 已经是操作员了");
            return;
        }
        
        // 添加操作员
        $success = $this->groupManager->addOperator($group['id'], $targetUser['id'], $addedBy['id']);
        
        if ($success) {
            $displayName = $this->userManager->getUserDisplayName($targetUser);
            $this->bot->sendMessage($chatId, "✅ 已将 {$displayName} 添加为操作员");
        } else {
            $this->bot->sendMessage($chatId, "❌ 添加操作员失败");
        }
    }
    
    /**
     * 通过用户名删除操作员
     */
    private function removeOperatorByUsername($chatId, $group, $username) {
        // 查找用户
        $targetUser = $this->db->fetch(
            "SELECT * FROM users WHERE username = :username",
            ['username' => $username]
        );
        
        if (!$targetUser) {
            $this->bot->sendMessage($chatId, "❌ 未找到用户 @{$username}");
            return;
        }
        
        // 检查是否是操作员
        if (!$this->groupManager->isOperator($group['id'], $targetUser['id'])) {
            $this->bot->sendMessage($chatId, "⚠️ @{$username} 不是操作员");
            return;
        }
        
        // 删除操作员
        $success = $this->groupManager->removeOperator($group['id'], $targetUser['id']);
        
        if ($success) {
            $displayName = $this->userManager->getUserDisplayName($targetUser);
            $this->bot->sendMessage($chatId, "✅ 已将 {$displayName} 从操作员中移除");
        } else {
            $this->bot->sendMessage($chatId, "❌ 删除操作员失败");
        }
    }
    
    /**
     * 删除所有操作员
     */
    private function removeAllOperators($chatId, $group) {
        $count = $this->db->fetch(
            "SELECT COUNT(*) as count FROM group_operators WHERE group_id = :group_id",
            ['group_id' => $group['id']]
        )['count'];
        
        if ($count == 0) {
            $this->bot->sendMessage($chatId, "⚠️ 当前没有操作员");
            return;
        }
        
        $success = $this->groupManager->removeAllOperators($group['id']);
        
        if ($success) {
            $this->bot->sendMessage($chatId, "✅ 已删除所有操作员 (共 {$count} 人)");
        } else {
            $this->bot->sendMessage($chatId, "❌ 删除操作员失败");
        }
    }
    
    /**
     * 显示操作员列表
     */
    private function showOperators($chatId, $group) {
        $operators = $this->groupManager->getOperators($group['id']);
        
        if (empty($operators)) {
            $this->bot->sendMessage($chatId, "📝 当前没有操作员");
            return;
        }
        
        $response = "👥 <b>操作员列表</b>\n";
        $response .= "━━━━━━━━━━━━━━━━━━━━━━\n\n";
        
        $count = 0;
        foreach ($operators as $operator) {
            $count++;
            $displayName = $this->userManager->getUserDisplayName($operator);
            $addedDate = date('Y-m-d', strtotime($operator['added_at']));
            
            $response .= "{$count}. {$displayName}\n";
            $response .= "   📅 添加时间: {$addedDate}\n\n";
        }
        
        $response .= "💡 总共 {$count} 位操作员";
        
        $this->bot->sendMessage($chatId, $response);
    }
    
    /**
     * 显示月度账单
     */
    private function showMonthlyBill($chatId, $group) {
        $startDate = date('Y-m-01 00:00:00');
        $endDate = date('Y-m-t 23:59:59');
        
        $summary = $this->accountingManager->getBillSummary($group['id'], $startDate, $endDate);
        
        $response = "📊 <b>本月总账单</b> (" . date('Y年m月') . ")\n";
        $response .= "━━━━━━━━━━━━━━━━━━━━━━\n\n";
        
        if (empty($summary)) {
            $response .= "📝 本月暂无交易记录";
            $this->bot->sendMessage($chatId, $response);
            return;
        }
        
        $totalIncome = 0;
        $totalExpense = 0;
        $totalDistribution = 0;
        
        foreach ($summary as $item) {
            switch ($item['transaction_type']) {
                case 'income':
                    $totalIncome = $item['total_amount'];
                    $incomeCount = $item['count'];
                    break;
                case 'expense':
                    $totalExpense = $item['total_amount'];
                    $expenseCount = $item['count'];
                    break;
                case 'distribution':
                    $totalDistribution = $item['total_amount'];
                    $distributionCount = $item['count'];
                    break;
            }
        }
        
        $response .= "💰 总入账: " . number_format($totalIncome, 2) . " CNY ({$incomeCount}笔)\n";
        $response .= "💸 总出账: " . number_format($totalExpense, 2) . " CNY ({$expenseCount}笔)\n";
        $response .= "📤 总下发: " . number_format($totalDistribution, 2) . " CNY ({$distributionCount}笔)\n\n";
        
        $netProfit = $totalIncome - $totalExpense - $totalDistribution;
        $profitIcon = $netProfit >= 0 ? '📈' : '📉';
        $response .= "{$profitIcon} 净收益: " . number_format($netProfit, 2) . " CNY\n";
        
        $this->bot->sendMessage($chatId, $response);
    }
    
    /**
     * 显示上月账单
     */
    private function showPreviousMonthBill($chatId, $group) {
        $startDate = date('Y-m-01 00:00:00', strtotime('first day of last month'));
        $endDate = date('Y-m-t 23:59:59', strtotime('last day of last month'));
        
        $summary = $this->accountingManager->getBillSummary($group['id'], $startDate, $endDate);
        
        $monthName = date('Y年m月', strtotime('last month'));
        $response = "📊 <b>上月总账单</b> ({$monthName})\n";
        $response .= "━━━━━━━━━━━━━━━━━━━━━━\n\n";
        
        if (empty($summary)) {
            $response .= "📝 上月暂无交易记录";
            $this->bot->sendMessage($chatId, $response);
            return;
        }
        
        $totalIncome = 0;
        $totalExpense = 0;
        $totalDistribution = 0;
        
        foreach ($summary as $item) {
            switch ($item['transaction_type']) {
                case 'income':
                    $totalIncome = $item['total_amount'];
                    $incomeCount = $item['count'];
                    break;
                case 'expense':
                    $totalExpense = $item['total_amount'];
                    $expenseCount = $item['count'];
                    break;
                case 'distribution':
                    $totalDistribution = $item['total_amount'];
                    $distributionCount = $item['count'];
                    break;
            }
        }
        
        $response .= "💰 总入账: " . number_format($totalIncome, 2) . " CNY ({$incomeCount}笔)\n";
        $response .= "💸 总出账: " . number_format($totalExpense, 2) . " CNY ({$expenseCount}笔)\n";
        $response .= "📤 总下发: " . number_format($totalDistribution, 2) . " CNY ({$distributionCount}笔)\n\n";
        
        $netProfit = $totalIncome - $totalExpense - $totalDistribution;
        $profitIcon = $netProfit >= 0 ? '📈' : '📉';
        $response .= "{$profitIcon} 净收益: " . number_format($netProfit, 2) . " CNY\n";
        
        $this->bot->sendMessage($chatId, $response);
    }
    
    /**
     * 显示操作员账单
     */
    private function showOperatorBill($chatId, $user, $group) {
        // 获取操作员操作的交易记录
        $transactions = $this->db->fetchAll(
            "SELECT * FROM transactions 
             WHERE group_id = :group_id AND operator_id = :operator_id AND is_deleted = 0
             ORDER BY created_at DESC LIMIT 20",
            ['group_id' => $group['id'], 'operator_id' => $user['id']]
        );
        
        $response = "👤 <b>我的操作记录</b>\n";
        $response .= "━━━━━━━━━━━━━━━━━━━━━━\n\n";
        
        if (empty($transactions)) {
            $response .= "📝 暂无操作记录";
            $this->bot->sendMessage($chatId, $response);
            return;
        }
        
        $count = 0;
        foreach ($transactions as $transaction) {
            $count++;
            $typeIcon = [
                'income' => '💰',
                'expense' => '💸',
                'distribution' => '📤'
            ][$transaction['transaction_type']] ?? '📊';
            
            $amount = number_format($transaction['amount'], 2);
            $date = date('m-d H:i', strtotime($transaction['created_at']));
            
            $response .= "{$count}. {$typeIcon} {$amount} CNY - {$date}\n";
            
            if ($count >= 10) break;
        }
        
        if (count($transactions) > 10) {
            $response .= "\n... 还有 " . (count($transactions) - 10) . " 条记录";
        }
        
        $this->bot->sendMessage($chatId, $response);
    }
    
    /**
     * 按用户名查看账单
     */
    private function showUserBillByName($chatId, $group, $targetName) {
        // 这里简化处理，实际应该支持多种查找方式
        $this->bot->sendMessage($chatId, "🔍 按用户名查询账单功能开发中...\n目前请使用 \"账单\" 查看群组账单");
    }
    
    /**
     * 重置账单
     */
    private function resetBill($chatId, $user, $group) {
        try {
            // 获取今日的交易数量
            $startDate = date('Y-m-d 00:00:00');
            $endDate = date('Y-m-d 23:59:59');
            
            $count = $this->db->fetch(
                "SELECT COUNT(*) as count FROM transactions 
                 WHERE group_id = :group_id AND is_deleted = 0 
                 AND created_at BETWEEN :start_date AND :end_date",
                [
                    'group_id' => $group['id'],
                    'start_date' => $startDate,
                    'end_date' => $endDate
                ]
            )['count'];
            
            if ($count == 0) {
                $this->bot->sendMessage($chatId, "⚠️ 今日暂无账单记录");
                return;
            }
            
            // 标记今日所有交易为已删除
            $deletedCount = $this->db->update(
                'transactions',
                ['is_deleted' => 1],
                'group_id = :group_id AND is_deleted = 0 AND created_at BETWEEN :start_date AND :end_date',
                [
                    'group_id' => $group['id'],
                    'start_date' => $startDate,
                    'end_date' => $endDate
                ]
            );
            
            // 清除账单哈希缓存
            $this->groupManager->setSetting($group['id'], 'last_bill_hash', '');
            
            $operatorName = $this->userManager->getUserDisplayName($user);
            $this->bot->sendMessage($chatId, "✅ 账单已重置\n📊 删除了 {$deletedCount} 条记录\n👤 操作员: {$operatorName}");
            
            // 强制发送新的空账单（不检查哈希）
            $newBill = $this->billFormatter->generateCustomBill($group['id']);
            $this->bot->sendMessage($chatId, $newBill);
            
            // 更新账单哈希
            $this->groupManager->setSetting($group['id'], 'last_bill_hash', md5($newBill));
            
        } catch (Exception $e) {
            $this->bot->sendMessage($chatId, '❌ 重置失败：' . $e->getMessage());
        }
    }
    
    /**
     * 发送群组加入消息
     */
    private function sendGroupJoinMessage($chatId, $chatInfo) {
        $message = "🤖 <b>记账机器人已加入群组！</b>\n\n";
        $message .= "如需记账请回复 <code>/start</code>\n\n";
        $message .= "📊 <b>群组信息：</b>\n";
        $message .= "群组名称：{$chatInfo['title']}\n";
        $message .= "群组ID：{$chatId}\n";
        $message .= "群组类型：{$chatInfo['type']}\n";
        
        $this->bot->sendMessage($chatId, $message);
    }
    
    /**
     * 发送群组欢迎消息和引导教程
     */
    private function sendGroupWelcomeMessage($chatId, $chatInfo) {
        $welcomeText = "🤖 <b>欢迎使用记账助手机器人！</b>\n\n";
        
        $welcomeText .= "📋 <b>获取群组ID教程：</b>\n\n";
        
        $welcomeText .= "如果你已经把你的机器人加入到目标群组，可以使用以下步骤：\n\n";
        
        $welcomeText .= "1️⃣ <b>机器人加入群组</b>\n";
        $welcomeText .= "把你的机器人拉进群组\n";
        $welcomeText .= "必须给机器人至少读取消息的权限\n";
        $welcomeText .= "如果是超级群（Supergroup）或频道，群 ID 通常是负数（例如 -100xxxxxxxxxx）。\n\n";
        
        $welcomeText .= "2️⃣ <b>使用 getUpdates 方法</b>\n";
        $welcomeText .= "在浏览器或命令行访问：\n";
        $welcomeText .= "https://api.telegram.org/bot<你的BOT_TOKEN>/getUpdates\n\n";
        
        $welcomeText .= "示例：\n";
        $welcomeText .= "https://api.telegram.org/bot7633773752:AAGk1dpUP-MIzN5DlxM9jrAp-DLKJ_0bOaQ/getUpdates\n\n";
        
        $welcomeText .= "然后在群里随便发一条消息（比如\"test\"），再刷新上面的 URL。\n";
        $welcomeText .= "返回的 JSON 里会有类似：\n\n";
        
        $welcomeText .= "{\n";
        $welcomeText .= "  \"update_id\":123456789,\n";
        $welcomeText .= "  \"message\":{\n";
        $welcomeText .= "    \"message_id\":1,\n";
        $welcomeText .= "    \"from\":{\"id\":111111111,\"first_name\":\"User\"},\n";
        $welcomeText .= "    \"chat\":{\n";
        $welcomeText .= "      \"id\":-1009876543210,\n";
        $welcomeText .= "      \"title\":\"我的测试群\",\n";
        $welcomeText .= "      \"type\":\"supergroup\"\n";
        $welcomeText .= "    },\n";
        $welcomeText .= "    \"date\":1660000000,\n";
        $welcomeText .= "    \"text\":\"test\"\n";
        $welcomeText .= "  }\n";
        $welcomeText .= "}\n\n";
        
        $welcomeText .= "👉 <b>群组 ID 就是 chat.id</b>\n\n";
        
        $welcomeText .= "📊 <b>当前群组信息：</b>\n";
        $welcomeText .= "群组名称：{$chatInfo['title']}\n";
        $welcomeText .= "群组ID：{$chatId}\n";
        $welcomeText .= "群组类型：{$chatInfo['type']}\n\n";
        
        $welcomeText .= "💡 <b>使用说明：</b>\n";
        $welcomeText .= "• 发送 /help 查看完整帮助\n";
        $welcomeText .= "• 发送 /start 开始使用\n";
        $welcomeText .= "• 发送 开始记账 启用记账功能\n";
        
        $this->bot->sendMessage($chatId, $welcomeText);
    }
    
    /**
     * 发送激活提示消息
     */
    private function sendActivationPrompt($chatId, $group) {
        $activationText = "🤖 <b>机器人需要激活才能使用记账功能！</b>\n\n";
        $activationText .= "如需记账请回复 <code>/start</code>\n\n";
        $activationText .= "📊 <b>群组ID：</b>{$chatId}";
        
        $this->bot->sendMessage($chatId, $activationText);
    }
    
    /**
     * 处理群组中的/start命令
     */
    private function handleGroupStartCommand($chatId, $user, $group) {
        $setupCompleted = $this->groupManager->getSetting($group['id'], 'setup_completed', 0);
        
        if (!$setupCompleted) {
            // 开始设置流程
            $this->startSetupProcess($chatId, $user, $group);
        } else {
            // 设置已完成，激活记账功能
            $this->activateAccounting($chatId, $group);
        }
    }
    
    /**
     * 开始设置流程
     */
    private function startSetupProcess($chatId, $user, $group) {
        $setupText = "🔧 <b>开始设置记账机器人</b>\n\n";
        $setupText .= "📋 <b>设置步骤：</b>\n";
        $setupText .= "1️⃣ 设置费率（默认70%）\n";
        $setupText .= "2️⃣ 设置汇率（默认7.2）\n";
        $setupText .= "3️⃣ 添加操作员\n\n";
        $setupText .= "💡 <b>请按顺序完成设置：</b>\n\n";
        $setupText .= "第一步：设置费率\n";
        $setupText .= "发送：<code>设置费率70</code>\n\n";
        $setupText .= "第二步：设置汇率\n";
        $setupText .= "发送：<code>设置汇率7.2</code>\n\n";
        $setupText .= "第三步：添加操作员\n";
        $setupText .= "发送：<code>@用户名 添加操作员</code>\n\n";
        $setupText .= "完成所有设置后，发送 <code>完成设置</code> 开始记账！\n\n";
        $setupText .= "📊 <b>群组ID：</b>{$chatId}";
        
        $this->bot->sendMessage($chatId, $setupText);
    }
    
    /**
     * 激活记账功能
     */
    private function activateAccounting($chatId, $group) {
        // 启用记账功能
        $this->groupManager->setAccountingStatus($group['id'], true);
        
        // 设置群组数字ID用于消息链接
        $this->billFormatter->setGroupTelegramId($group['id'], $chatId);
        
        $activationMessage = "✅ <b>记账功能已激活！</b>\n\n";
        $activationMessage .= "📊 <b>群组信息：</b>\n";
        $activationMessage .= "群组ID：{$chatId}\n";
        $activationMessage .= "状态：已激活\n\n";
        $activationMessage .= "💡 <b>现在可以使用：</b>\n";
        $activationMessage .= "• 记账：+100, -50, 下发等\n";
        $activationMessage .= "• 查看账单：账单, 总账单\n";
        $activationMessage .= "• 重置账单：重置, 清零\n\n";
        $activationMessage .= "🎉 记账开始，金额链接可点击跳转！";
        
        $this->bot->sendMessage($chatId, $activationMessage);
    }
    
    /**
     * 完成设置
     */
    private function completeSetup($chatId, $user, $group) {
        // 检查是否已完成必要设置
        $feeRate = $this->groupManager->getSetting($group['id'], 'fee_rate', 70);
        $exchangeRate = $this->groupManager->getSetting($group['id'], 'exchange_rate', 7.2);
        $operators = $this->groupManager->getOperators($group['id']);
        
        $setupText = "🔍 <b>检查设置状态</b>\n\n";
        $setupText .= "📊 <b>当前设置：</b>\n";
        $setupText .= "费率：{$feeRate}%\n";
        $setupText .= "汇率：{$exchangeRate}\n";
        $setupText .= "操作员数量：" . count($operators) . "人\n\n";
        
        if (count($operators) == 0) {
            $setupText .= "❌ <b>设置未完成！</b>\n";
            $setupText .= "请先添加至少一个操作员：\n";
            $setupText .= "<code>@用户名 添加操作员</code>\n\n";
            $setupText .= "完成后再发送 <code>完成设置</code>";
        } else {
            // 标记设置完成
            $this->groupManager->setSetting($group['id'], 'setup_completed', 1);
            
            // 激活记账功能
            $this->activateAccounting($chatId, $group);
            return;
        }
        
        $this->bot->sendMessage($chatId, $setupText);
    }
}
