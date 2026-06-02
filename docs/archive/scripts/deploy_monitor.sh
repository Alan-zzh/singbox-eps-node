#!/bin/bash
# ============================================================
# 部署服务清理 + 健康监控脚本
# 功能:
#   1. 更新 singbox-sub.service（加入启动前端口清理）
#   2. 安装 health_monitor.py（每 5 分钟检查服务 + 邮件报警）
#   3. 安装 singbox-monitor.service（开机自启监控）
#   4. 配置报警邮箱（从 .env 读取）
# 用法: bash deploy_monitor.sh
# ============================================================

set -e

echo "===== singbox 服务清理 + 监控部署 ====="

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_DIR="$SCRIPT_DIR/deploy"

# 读取 .env
if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
else
    echo "错误: .env 不存在"
    exit 1
fi

echo "目标服务器: $SERVER_IP"

# 1. 同步脚本
echo "[1/5] 同步脚本到服务器..."
scp -o StrictHostKeyChecking=no "$SCRIPT_DIR/scripts/health_monitor.py" root@$SERVER_IP:/root/singbox-eps-node/scripts/
echo "  ✅ health_monitor.py 已同步"

# 2. 同步 systemd 服务文件
echo "[2/5] 更新 systemd 服务配置..."
scp -o StrictHostKeyChecking=no "$DEPLOY_DIR/singbox-sub.service" root@$SERVER_IP:/etc/systemd/system/singbox-sub.service
scp -o StrictHostKeyChecking=no "$DEPLOY_DIR/singbox-monitor.service" root@$SERVER_IP:/etc/systemd/system/singbox-monitor.service
echo "  ✅ 服务配置已更新"

# 3. SSH 执行部署
echo "[3/5] 在服务器上执行部署..."
ssh -o StrictHostKeyChecking=no root@$SERVER_IP << 'EOF'
# 清理旧进程
pkill -9 -f "subscription_service.py" 2>/dev/null || true
sleep 2

# 重新加载 systemd
systemctl daemon-reload

# 重启订阅服务
systemctl restart singbox-sub
echo "  singbox-sub: $(systemctl is-active singbox-sub)"

# 启动监控服务
systemctl enable singbox-monitor
systemctl start singbox-monitor
echo "  singbox-monitor: $(systemctl is-active singbox-monitor)"

# 验证端口清理逻辑
echo ""
echo "=== 验证 singbox-sub.service 的清理逻辑 ==="
grep "ExecStartPre" /etc/systemd/system/singbox-sub.service || echo "  未找到 ExecStartPre!"

# 验证服务状态
echo ""
echo "=== 当前服务状态 ==="
systemctl status singbox-sub --no-pager | head -5
echo ""
systemctl status singbox-monitor --no-pager | head -5
EOF

echo "[4/5] 验证订阅服务..."
sleep 3
ssh -o StrictHostKeyChecking=no root@$SERVER_IP "curl -sk https://127.0.0.1:$SUB_PORT/singbox/$COUNTRY_CODE | python3 -c 'import sys,json; c=json.load(sys.stdin); obs=c.get(\"outbounds\",[]); print(f\"  Outbounds: {len(obs)}\")'" 2>/dev/null || echo "  ⚠️ 验证失败"

echo "[5/5] 部署完成！"

echo ""
echo "===== 配置摘要 ====="
echo "监控间隔: ${MONITOR_CHECK_INTERVAL:-300}秒"
echo "重启报警阈值: ${MONITOR_RESTART_THRESHOLD:-10}次"
echo "报警邮箱: ${MONITOR_ALERT_EMAIL:-未配置}"
echo ""
echo "监控服务每 ${MONITOR_CHECK_INTERVAL:-300} 秒检查一次服务状态"
echo "重启次数超过 ${MONITOR_RESTART_THRESHOLD:-10} 次时会发送邮件报警"
echo "端口被占用时会自动清理并重启服务"
echo ""
echo "手动查看监控日志: journalctl -u singbox-monitor -f"
echo "手动测试报警: python3 /root/singbox-eps-node/scripts/health_monitor.py（按 Ctrl+C 停止）"
