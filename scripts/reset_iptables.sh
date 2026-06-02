#!/bin/bash
# ============================================================
# iptables 流量计数器月度归零脚本
# 版本: v4.10.20.1
# 用途: 每月 3 号 00:03 自动清零 INPUT/OUTPUT 计数器
# Cron: 3 0 3 * * /root/singbox-eps-node/scripts/reset_iptables.sh >> /var/log/iptables_reset.log 2>&1
# 部署: install.sh 阶段 4 自动添加 cron + 写本脚本
# ============================================================

iptables -Z INPUT
iptables -Z OUTPUT
echo "[$(date '+%F %T')] iptables 流量计数器已归零" >> /var/log/iptables_reset.log
