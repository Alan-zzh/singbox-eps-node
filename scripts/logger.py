#!/usr/bin/env python3
"""
日志模块
Author: Alan
Version: v1.0.3
Date: 2026-04-20
功能：统一的日志管理
"""

import os
import logging
import sys
from datetime import datetime

LOG_DIR = '/var/log'
LOG_FILE = os.path.join(LOG_DIR, 'singbox.log')

def setup_logger(name, log_file=None, level=logging.INFO):
    """创建日志记录器"""
    if log_file is None:
        log_file = LOG_FILE

    os.makedirs(os.path.dirname(log_file) if os.path.dirname(log_file) else '.', exist_ok=True)

    formatter = logging.Formatter(
        '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    handler = logging.FileHandler(log_file, encoding='utf-8')
    handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.addHandler(console_handler)

    return logger

def get_logger(name):
    """获取日志记录器"""
    return logging.getLogger(name) if logging.getLogger(name).handlers else setup_logger(name)
