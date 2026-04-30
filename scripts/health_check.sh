#!/bin/bash
# ============================================================
# singbox-eps-node 服务健康检查与自动修复脚本
# 版本: v3.1.2
# 日期: 2026-05-01
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
# 0. config.json自愈检查（最关键，必须在服务检查之前）
# ⚠️ Bug #48教训：config.json被删导致singbox无限重启FATAL
# 必须在check_services之前执行，否则重启singbox也是白搭
# ============================================================
check_config_json() {
    log "--- config.json自愈检查 ---"
    if [ -f "$BASE_DIR/config.json" ]; then
        SIZE=$(stat -c%s "$BASE_DIR/config.json" 2>/dev/null || echo "0")
        if [ "$SIZE" -gt 100 ]; then
            # v3.1.2: 增加JSON语法校验，防止损坏的config.json导致singbox FATAL
            SYNTAX_OK=$(python3 -c "import json; json.load(open('$BASE_DIR/config.json'))" 2>/dev/null && echo "ok" || echo "fail")
            if [ "$SYNTAX_OK" = "ok" ]; then
                log "  config.json: ✅ 存在且语法正确 (${SIZE}字节)"
                return 0
            else
                log "  config.json: ❌ 语法损坏，自动重新生成..."
                cd "$BASE_DIR" && python3 scripts/config_generator.py >> "$LOG_FILE" 2>&1
                if [ -f "$BASE_DIR/config.json" ]; then
                    log "  config.json: ✅ 已恢复"
                    systemctl restart singbox 2>/dev/null || true
                else
                    log "  config.json: ❌ 自动生成失败，需要人工介入"
                fi
            fi
        fi
    else
        log "  config.json: ❌ 不存在，自动重新生成..."
        cd "$BASE_DIR" && python3 scripts/config_generator.py >> "$LOG_FILE" 2>&1
        if [ -f "$BASE_DIR/config.json" ]; then
            SIZE=$(stat -c%s "$BASE_DIR/config.json" 2>/dev/null || echo "0")
            log "  config.json: ✅ 已恢复 (${SIZE}字节)"
            systemctl restart singbox 2>/dev/null || true
        else
            log "  config.json: ❌ 自动生成失败，需要人工介入"
        fi
    fi
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

    for svc in singbox singbox-sub singbox-cdn; do
        if systemctl is-active --quiet "$svc"; then
            log "  $svc: ✅ 运行中"
        else
            log "  $svc: ❌ 未运行，尝试重启..."
            systemctl restart "$svc"
            sleep 3
            if systemctl is-active --quiet "$svc"; then
                log "  $svc: ✅ 重启成功"
            else
                log "  $svc: ❌ 重启失败，需要人工介入"
            fi
        fi
    done
}

# ============================================================
# 3. 端口监听检查
# ============================================================
check_ports() {
    log "--- 端口监听检查 ---"
    for port in 443 8443 2053 2083 2087; do
        if ss -tlnp | grep -q ":$port "; then
            log "  端口 $port/TCP: ✅ 监听中"
        else
            log "  端口 $port/TCP: ❌ 未监听"
        fi
    done
    if ss -ulnp | grep -q ":443 "; then
        log "  端口 443/UDP: ✅ 监听中 (HY2/QUIC)"
    else
        log "  端口 443/UDP: ❌ 未监听 (HY2/QUIC不可用)"
    fi
}

# ============================================================
# 4. 订阅接口可用性检查
# ⚠️ 本地localhost测试用-k是合理的（证书颁发给域名，localhost域名不匹配）
# 但同时需要验证域名访问的证书是否正常
# ============================================================
check_subscription() {
    log "--- 订阅接口检查 ---"

    COUNTRY=$(grep "^COUNTRY_CODE=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "US")
    # v3.1.2: 端口从config.py读取，不硬编码2087
    SUB_PORT=$(python3 -c "import sys; sys.path.insert(0,'$BASE_DIR/scripts'); from config import SUB_PORT; print(SUB_PORT)" 2>/dev/null || echo "2087")

    RESPONSE=$(curl -sk --connect-timeout 5 "https://localhost:${SUB_PORT}/sub/${COUNTRY}" 2>&1)
    if [ -n "$RESPONSE" ] && [ ${#RESPONSE} -gt 50 ]; then
        log "  订阅接口(本地): ✅ 正常 (返回${#RESPONSE}字节)"
    else
        log "  订阅接口(本地): ❌ 异常，尝试重启订阅服务..."
        systemctl restart singbox-sub
        sleep 5
        RESPONSE2=$(curl -sk --connect-timeout 5 "https://localhost:${SUB_PORT}/sub/${COUNTRY}" 2>&1)
        if [ -n "$RESPONSE2" ] && [ ${#RESPONSE2} -gt 50 ]; then
            log "  订阅接口(本地): ✅ 重启后恢复 (返回${#RESPONSE2}字节)"
        else
            log "  订阅接口(本地): ❌ 重启后仍异常，需要人工介入"
        fi
    fi

    CF_DOMAIN=$(grep "^CF_DOMAIN=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
    if [ -n "$CF_DOMAIN" ]; then
        DOMAIN_RESPONSE=$(curl -s --connect-timeout 5 "https://${CF_DOMAIN}:${SUB_PORT}/sub/${COUNTRY}" 2>&1)
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
    CERT_FILE=""
    for f in "$BASE_DIR/cert/fullchain.pem" "$BASE_DIR/cert/cert.pem"; do
        if [ -f "$f" ]; then
            CERT_FILE="$f"
            break
        fi
    done
    if [ -n "$CERT_FILE" ]; then
        EXPIRY=$(openssl x509 -enddate -noout -in "$CERT_FILE" 2>/dev/null | cut -d= -f2)
        EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s 2>/dev/null)
        NOW_EPOCH=$(date +%s)
        DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
        if [ "$DAYS_LEFT" -gt 30 ]; then
            log "  证书有效期: ✅ 剩余${DAYS_LEFT}天 (到期: $EXPIRY, 文件: $(basename $CERT_FILE))"
        elif [ "$DAYS_LEFT" -gt 0 ]; then
            log "  证书有效期: ⚠️ 剩余${DAYS_LEFT}天，即将过期！ (到期: $EXPIRY)"
        else
            log "  证书有效期: ❌ 已过期！需要立即续期"
        fi
    else
        log "  证书文件: ❌ 不存在 (fullchain.pem 和 cert.pem 均未找到)"
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
# 8. Swap检查（Bug #39教训：414MB小内存VPS必须配Swap）
# ============================================================
check_swap() {
    log "--- Swap检查 ---"
    SWAP_TOTAL=$(free -m 2>/dev/null | awk '/^Swap:/{print $2}')
    SWAP_USED=$(free -m 2>/dev/null | awk '/^Swap:/{print $3}')
    if [ -z "$SWAP_TOTAL" ]; then
        log "  Swap: ⚠️ 无法读取Swap信息"
        return
    fi
    if [ "$SWAP_TOTAL" -eq 0 ]; then
        log "  Swap: ❌ 未配置Swap！小内存VPS必须配Swap防止OOM killer杀进程"
    elif [ "$SWAP_TOTAL" -lt 1024 ]; then
        log "  Swap: ⚠️ Swap仅${SWAP_TOTAL}MB，建议至少2GB"
    else
        log "  Swap: ✅ ${SWAP_USED}MB/${SWAP_TOTAL}MB"
    fi
}

# ============================================================
# 9. iptables流量计数器检查（v3.1.1新增）
# ============================================================
check_iptables_traffic() {
    log "--- iptables流量计数器检查 ---"
    # 检查singbox入站端口的iptables计数器是否存在
    MISSING_PORTS=""
    for port in 443 8443 2053 2083; do
        COUNT=$(iptables -L INPUT -v -n -x 2>/dev/null | grep -c "dpt:$port " || echo "0")
        if [ "$COUNT" -ge 1 ]; then
            log "  流量计数器 $port: ✅ 存在"
        else
            log "  流量计数器 $port: ❌ 缺失"
            MISSING_PORTS="$MISSING_PORTS $port"
        fi
    done
    if [ -n "$MISSING_PORTS" ]; then
        log "  ⚠️ 缺失端口的流量统计不可用，建议运行 subscription_service.py 初始化计数器"
    fi
}

# ============================================================
# 主流程
# ============================================================
log "=========================================="
log "singbox-eps-node 健康检查开始"
log "=========================================="

check_config_json
check_port_integrity
check_services
check_ports
check_subscription
check_firewall
check_cert
check_disk
check_swap
check_iptables_traffic

log "=========================================="
log "健康检查完成"
log "=========================================="
