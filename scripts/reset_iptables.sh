#!/bin/bash
# ============================================================
# [Codex] iptables 流量统计基准说明脚本
# 版本: v4.12.2
# 用途: 保留兼容入口，但不清零内核计数器
# 说明: subscription_service.py 每月 14 号通过数据库 baseline 重置月用量
# ============================================================

echo "[$(date '+%F %T')] [Codex] 不清零 iptables 内核计数器；月度流量由 subscription_service.py baseline 重置" >> /var/log/iptables_reset.log
