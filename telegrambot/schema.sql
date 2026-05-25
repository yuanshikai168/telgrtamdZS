-- Telegram记账机器人数据库结构

-- 用户表
CREATE TABLE IF NOT EXISTS `users` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `telegram_id` bigint(20) NOT NULL UNIQUE,
    `username` varchar(100) DEFAULT NULL,
    `first_name` varchar(100) DEFAULT NULL,
    `last_name` varchar(100) DEFAULT NULL,
    `permission_level` tinyint(1) DEFAULT 3 COMMENT '0=超级管理员 1=管理员 2=操作员 3=普通用户',
    `is_active` tinyint(1) DEFAULT 1,
    `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
    `updated_at` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_telegram_id` (`telegram_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 群组表
CREATE TABLE IF NOT EXISTS `groups` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `telegram_group_id` bigint(20) NOT NULL UNIQUE,
    `group_name` varchar(200) DEFAULT NULL,
    `group_type` varchar(20) DEFAULT 'group',
    `is_active` tinyint(1) DEFAULT 1,
    `accounting_status` tinyint(1) DEFAULT 1,
    `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
    `updated_at` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_group_id` (`telegram_group_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 群组操作员表
CREATE TABLE IF NOT EXISTS `group_operators` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `group_id` int(11) NOT NULL,
    `user_id` int(11) NOT NULL,
    `added_by` int(11) DEFAULT NULL,
    `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `unique_group_user` (`group_id`, `user_id`),
    FOREIGN KEY (`group_id`) REFERENCES `groups`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 交易记录表
CREATE TABLE IF NOT EXISTS `transactions` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `group_id` int(11) NOT NULL,
    `user_id` int(11) NOT NULL,
    `operator_id` int(11) NOT NULL,
    `message_id` int(11) DEFAULT NULL,
    `transaction_type` enum('income','expense','distribution','correction') NOT NULL,
    `amount` decimal(15,2) NOT NULL,
    `original_amount` decimal(15,2) DEFAULT NULL,
    `fee_rate` decimal(5,2) DEFAULT NULL,
    `exchange_rate` decimal(10,4) DEFAULT NULL,
    `currency` varchar(10) DEFAULT 'CNY',
    `category` varchar(50) DEFAULT NULL,
    `note` text,
    `is_pending` tinyint(1) DEFAULT 0,
    `is_deleted` tinyint(1) DEFAULT 0,
    `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
    `updated_at` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_group_date` (`group_id`, `created_at`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_operator_id` (`operator_id`),
    FOREIGN KEY (`group_id`) REFERENCES `groups`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 群组设置表
CREATE TABLE IF NOT EXISTS `group_settings` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `group_id` int(11) NOT NULL,
    `setting_key` varchar(50) NOT NULL,
    `setting_value` text,
    `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
    `updated_at` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `unique_group_setting` (`group_id`, `setting_key`),
    FOREIGN KEY (`group_id`) REFERENCES `groups`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 自定义汇率表
CREATE TABLE IF NOT EXISTS `custom_rates` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `group_id` int(11) NOT NULL,
    `rate_name` varchar(20) NOT NULL,
    `fee_rate` decimal(5,2) DEFAULT NULL,
    `exchange_rate` decimal(10,4) DEFAULT NULL,
    `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
    `updated_at` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `unique_group_rate` (`group_id`, `rate_name`),
    FOREIGN KEY (`group_id`) REFERENCES `groups`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 群组按钮表
CREATE TABLE IF NOT EXISTS `group_buttons` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `group_id` int(11) NOT NULL,
    `button_text` varchar(50) NOT NULL,
    `button_url` varchar(500) NOT NULL,
    `button_type` varchar(20) DEFAULT 'url',
    `sort_order` int(11) DEFAULT 0,
    `is_active` tinyint(1) DEFAULT 1,
    `created_at` timestamp DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    FOREIGN KEY (`group_id`) REFERENCES `groups`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;