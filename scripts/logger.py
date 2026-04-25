#!/usr/bin/env python3
"""
日志模块
Author: Alan
Version: v2.0.0
Date: 2026-04-20
功能：统一的日志管理，带自动滚动和大小限制
"""

import os
import logging
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime

# 日志配置 - 自动检测当前脚本所在目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'singbox.log')
MAX_LOG_SIZE = 50 * 1024 * 1024  # 50MB
BACKUP_COUNT = 2  # 保留2个备份

def setup_logger(name, log_file=None, level=logging.INFO):
    """创建日志记录器，带自动滚动功能"""
    if log_file is None:
        log_file = LOG_FILE

    os.makedirs(os.path.dirname(log_file) if os.path.dirname(log_file) else '.', exist_ok=True)

    formatter = logging.Formatter(
        '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 使用RotatingFileHandler自动限制日志文件大小
    handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 避免重复添加handler
    if not logger.handlers:
        logger.addHandler(handler)
        logger.addHandler(console_handler)

    return logger

def get_logger(name):
    """获取日志记录器"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
