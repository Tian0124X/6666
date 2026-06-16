-- 企业智能办公助手平台 — MySQL 初始化
CREATE TABLE IF NOT EXISTS conversations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    role ENUM('user', 'assistant', 'system') NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_user (session_id, user_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS task_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL UNIQUE,
    user_id VARCHAR(64) NOT NULL,
    task_type VARCHAR(32) NOT NULL,
    status ENUM('pending', 'running', 'success', 'failed', 'retrying') DEFAULT 'pending',
    input_params JSON,
    output_result JSON,
    error_log TEXT,
    retry_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_status (user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS eval_records (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    eval_type VARCHAR(20) NOT NULL COMMENT 'rag | agent',
    accuracy VARCHAR(20) NOT NULL COMMENT '准确率',
    avg_recall VARCHAR(20) NULL COMMENT 'RAG 平均召回率',
    tool_accuracy VARCHAR(20) NULL COMMENT 'Agent 工具准确率',
    avg_latency_ms VARCHAR(20) NOT NULL COMMENT '平均延迟',
    passed INT DEFAULT 0 COMMENT '通过数',
    total INT DEFAULT 0 COMMENT '总数',
    details_json TEXT NULL COMMENT '评测详情 JSON',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_eval_type (eval_type),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS analytics_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(32) NOT NULL COMMENT 'chat_start/chat_end/tool_call/rag_query/knowledge_upload/user_login',
    user_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NULL,
    data_json JSON NULL COMMENT '事件附加数据',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_event_type (event_type),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
