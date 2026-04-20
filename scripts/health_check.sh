#!/bin/bash
# ============================================================
# singbox-eps-node 服务健康检查与自动修复脚本
# 版本: v1.0.1
# 日期: 2026-04-21
# 用途: 启动前检查、定期健康检查、故障自动恢复
# 部署: 放置在 /root/singbox-eps-node/scripts/health_check.sh
# Cron: */5 * * * * /root/singbox-eps-node/scripts/health_check.sh >> /root/singbox-eps-node/logs/health_check.log 2>&1
# ============================================================

BASE_DIR="/root/singbox-eps-node"
LOG_DIR="$BASE_DIR/logs"
LOG_FILE="$LOG_DIR/health_check.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

mkdir -p "$LOG_DIR"

log() {
    echo "[$TIMESTAMP] $1" | tee -a "$LOG_FILE"
}

# ============================================================
# 1. 端口完整性校验
# ============================================================
check_port_integrity() {
    log "--- 端口完整性校验 ---"
    cd "$BASE_DIR"
    RESULT=$(python3 -c "
from scripts.config import verify_port_integrity, save_port_lock
is_valid, msg = verify_port_integrity()
if not is_valid:
    save_port_lock()
    print(f'FIXED: {msg}')
else:
    print(f'OK: {msg}')
" 2>&1)
    log "  端口校验: $RESULT"
}

# ============================================================
# 2. 服务状态检查与自动重启
# ============================================================
check_services() {
    log "--- 服务状态检查 ---"
    
    # singbox主服务
    if systemctl is-active --quiet singbox; then
        log "  singbox: ✅ 运行中"
    else
        log "  singbox: ❌ 未运行，尝试重启..."
        systemctl restart singbox
        sleep 3
        if systemctl is-active --quiet singbox; then
            log "  singbox: ✅ 重启成功"
        else
            log "  singbox: ❌ 重启失败，需要人工介入"
        fi
    fi

    # 订阅服务
    if systemctl is-active --quiet singbox-sub; then
        log "  singbox-sub: ✅ 运行中"
    else
        log "  singbox-sub: ❌ 未运行，尝试重启..."
        systemctl restart singbox-sub
        sleep 3
        if systemctl is-active --quiet singbox-sub; then
            log "  singbox-sub: ✅ 重启成功"
        else
            log "  singbox-sub: ❌ 重启失败，需要人工介入"
        fi
    fi

    # CDN监控
    if systemctl is-active --quiet singbox-cdn; then
        log "  singbox-cdn: ✅ 运行中"
    else
        log "  singbox-cdn: ❌ 未运行，尝试重启..."
        systemctl restart singbox-cdn
        sleep 3
        if systemctl is-active --quiet singbox-cdn; then
            log "  singbox-cdn: ✅ 重启成功"
        else
            log "  singbox-cdn: ❌ 重启失败，需要人工介入"
        fi
    fi
}

# ============================================================
# 3. 端口监听检查
# ============================================================
check_ports() {
    log "--- 端口监听检查 ---"
    for port in 443 8443 2053 2083 2087; do
        if ss -tlnp | grep -q ":$port "; then
            log "  端口 $port: ✅ 监听中"
        else
            log "  端口 $port: ❌ 未监听"
        fi
    done
}

# ============================================================
# 4. 订阅接口可用性检查
# ⚠️ 本地localhost测试用-k是合理的（证书颁发给域名，localhost域名不匹配）
# 但同时需要验证域名访问的证书是否正常
# ============================================================
check_subscription() {
    log "--- 订阅接口检查 ---"
    
    # 本地进程检查（不验证证书，因为localhost域名不匹配）
    RESPONSE=$(curl -sk --connect-timeout 5 https://localhost:2087/sub/JP 2>&1)
    if [ -n "$RESPONSE" ] && [ ${#RESPONSE} -gt 50 ]; then
        log "  订阅接口(本地): ✅ 正常 (返回${#RESPONSE}字节)"
    else
        log "  订阅接口(本地): ❌ 异常，尝试重启订阅服务..."
        systemctl restart singbox-sub
        sleep 5
        RESPONSE2=$(curl -sk --connect-timeout 5 https://localhost:2087/sub/JP 2>&1)
        if [ -n "$RESPONSE2" ] && [ ${#RESPONSE2} -gt 50 ]; then
            log "  订阅接口(本地): ✅ 重启后恢复 (返回${#RESPONSE2}字节)"
        else
            log "  订阅接口(本地): ❌ 重启后仍异常，需要人工介入"
        fi
    fi

    # 域名访问检查（验证SSL证书是否匹配，不使用-k，模拟真实客户端）
    CF_DOMAIN=$(grep "^CF_DOMAIN=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
    if [ -n "$CF_DOMAIN" ]; then
        DOMAIN_RESPONSE=$(curl -s --connect-timeout 5 "https://${CF_DOMAIN}:2087/sub/JP" 2>&1)
        CURL_EXIT=$?
        if [ $CURL_EXIT -eq 0 ] && [ -n "$DOMAIN_RESPONSE" ] && [ ${#DOMAIN_RESPONSE} -gt 50 ]; then
            log "  订阅接口(域名${CF_DOMAIN}): ✅ 证书匹配，正常访问"
        elif [ $CURL_EXIT -eq 60 ]; then
            log "  订阅接口(域名${CF_DOMAIN}): ❌ SSL证书不匹配！需要检查证书配置"
        else
            log "  订阅接口(域名${CF_DOMAIN}): ⚠️ 无法通过域名访问（exit=$CURL_EXIT），可能CDN未配置"
        fi
    fi
}

# ============================================================
# 5. 防火墙状态检查（确保默认全放行）
# ============================================================
check_firewall() {
    log "--- 防火墙状态检查 ---"
    POLICY=$(iptables -L INPUT -n | head -1 | grep -o 'policy [A-Z]*' | awk '{print $2}')
    if [ "$POLICY" = "ACCEPT" ]; then
        log "  防火墙默认策略: ✅ ACCEPT (全放行)"
    else
        log "  防火墙默认策略: ❌ $POLICY，修正为ACCEPT..."
        iptables -P INPUT ACCEPT
        iptables -F INPUT
        log "  防火墙已修正为: ACCEPT (全放行)"
    fi
}

# ============================================================
# 6. 证书有效期检查
# ============================================================
check_cert() {
    log "--- 证书有效期检查 ---"
    CERT_FILE="$BASE_DIR/cert/fullchain.pem"
    if [ -f "$CERT_FILE" ]; then
        EXPIRY=$(openssl x509 -enddate -noout -in "$CERT_FILE" 2>/dev/null | cut -d= -f2)
        EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s 2>/dev/null)
        NOW_EPOCH=$(date +%s)
        DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
        if [ "$DAYS_LEFT" -gt 30 ]; then
            log "  证书有效期: ✅ 剩余${DAYS_LEFT}天 (到期: $EXPIRY)"
        elif [ "$DAYS_LEFT" -gt 0 ]; then
            log "  证书有效期: ⚠️ 剩余${DAYS_LEFT}天，即将过期！ (到期: $EXPIRY)"
        else
            log "  证书有效期: ❌ 已过期！需要立即续期"
        fi
    else
        log "  证书文件: ❌ 不存在"
    fi
}

# ============================================================
# 7. 磁盘空间检查
# ============================================================
check_disk() {
    log "--- 磁盘空间检查 ---"
    USAGE=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%')
    if [ "$USAGE" -lt 80 ]; then
        log "  磁盘使用: ✅ ${USAGE}%"
    elif [ "$USAGE" -lt 90 ]; then
        log "  磁盘使用: ⚠️ ${USAGE}%，需要清理"
    else
        log "  磁盘使用: ❌ ${USAGE}%，严重不足！"
    fi
}

# ============================================================
# 主流程
# ============================================================
log "=========================================="
log "singbox-eps-node 健康检查开始"
log "=========================================="

check_port_integrity
check_services
check_ports
check_subscription
check_firewall
check_cert
check_disk

log "=========================================="
log "健康检查完成"
log "=========================================="
