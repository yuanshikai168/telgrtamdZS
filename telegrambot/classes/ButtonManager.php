<?php
/**
 * 按钮管理类 - 处理多按钮配置
 */

require_once 'classes/Database.php';

class ButtonManager {
    private $db;
    
    public function __construct() {
        $this->db = Database::getInstance();
    }
    
    /**
     * 获取群组的所有按钮
     */
    public function getGroupButtons($groupId) {
        $sql = "SELECT * FROM group_buttons 
                WHERE group_id = ? AND is_active = 1 
                ORDER BY sort_order ASC, id ASC";
        
        return $this->db->fetchAll($sql, [$groupId]);
    }
    
    /**
     * 添加按钮
     */
    public function addButton($groupId, $buttonText, $buttonUrl, $buttonType = 'url', $sortOrder = 0) {
        $data = [
            'group_id' => $groupId,
            'button_text' => $buttonText,
            'button_url' => $buttonUrl,
            'button_type' => $buttonType,
            'sort_order' => $sortOrder,
            'is_active' => 1
        ];
        
        return $this->db->insert('group_buttons', $data);
    }
    
    /**
     * 更新按钮
     */
    public function updateButton($buttonId, $buttonText, $buttonUrl, $buttonType = 'url', $sortOrder = 0) {
        $data = [
            'button_text' => $buttonText,
            'button_url' => $buttonUrl,
            'button_type' => $buttonType,
            'sort_order' => $sortOrder
        ];
        
        return $this->db->update('group_buttons', $data, 'id = ?', [$buttonId]);
    }
    
    /**
     * 删除按钮
     */
    public function deleteButton($buttonId) {
        return $this->db->delete('group_buttons', 'id = ?', [$buttonId]);
    }
    
    /**
     * 启用/禁用按钮
     */
    public function toggleButton($buttonId, $isActive) {
        $data = ['is_active' => $isActive ? 1 : 0];
        return $this->db->update('group_buttons', $data, 'id = ?', [$buttonId]);
    }
    
    /**
     * 更新按钮排序
     */
    public function updateButtonOrder($buttonId, $sortOrder) {
        $data = ['sort_order' => $sortOrder];
        return $this->db->update('group_buttons', $data, 'id = ?', [$buttonId]);
    }
    
    /**
     * 生成Telegram内联键盘
     */
    public function generateInlineKeyboard($groupId) {
        $buttons = $this->getGroupButtons($groupId);
        
        if (empty($buttons)) {
            // 如果没有配置按钮，使用默认按钮
            $groupToken = md5($groupId . 'telegram_bot_token_2024');
            $baseUrl = $this->getBaseUrl();
            $defaultUrl = $baseUrl . "/bill_detail.php?token=" . $groupToken . "&group_id=" . $groupId;
            
            return [
                'inline_keyboard' => [
                    [
                        [
                            'text' => '📊 查看详情',
                            'url' => $defaultUrl
                        ]
                    ]
                ]
            ];
        }
        
        // 按行组织按钮（每行最多2个按钮）
        $keyboard = ['inline_keyboard' => []];
        $currentRow = [];
        
        foreach ($buttons as $button) {
            $buttonData = [
                'text' => $button['button_text'],
                'url' => $button['button_url']
            ];
            
            if ($button['button_type'] === 'callback') {
                $buttonData = [
                    'text' => $button['button_text'],
                    'callback_data' => $button['button_url']
                ];
            }
            
            $currentRow[] = $buttonData;
            
            // 每行最多2个按钮
            if (count($currentRow) >= 2) {
                $keyboard['inline_keyboard'][] = $currentRow;
                $currentRow = [];
            }
        }
        
        // 添加最后一行
        if (!empty($currentRow)) {
            $keyboard['inline_keyboard'][] = $currentRow;
        }
        
        return $keyboard;
    }
    
    /**
     * 获取基础URL
     */
    private function getBaseUrl() {
        $protocol = isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on' ? 'https' : 'http';
        $host = $_SERVER['HTTP_HOST'] ?? 'localhost';
        $path = dirname($_SERVER['REQUEST_URI'] ?? '');
        return $protocol . '://' . $host . $path;
    }
    
    /**
     * 获取按钮统计
     */
    public function getButtonStats($groupId) {
        $stats = $this->db->fetch("
            SELECT 
                COUNT(*) as total_buttons,
                SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active_buttons,
                SUM(CASE WHEN button_type = 'url' THEN 1 ELSE 0 END) as url_buttons,
                SUM(CASE WHEN button_type = 'callback' THEN 1 ELSE 0 END) as callback_buttons
            FROM group_buttons 
            WHERE group_id = ?
        ", [$groupId]);
        
        return $stats ?: [
            'total_buttons' => 0,
            'active_buttons' => 0,
            'url_buttons' => 0,
            'callback_buttons' => 0
        ];
    }
}
