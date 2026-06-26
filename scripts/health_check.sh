#!/bin/bash
# ============================================================
# singbox-eps-node 统一健康检查与资源守护脚本
# 版本: v4.10.20
# 用途: 详细日志版（之前只输出"开始/完成"两行，无法审计）
# Cron: */15 * * * * /root/singbox-eps-node/scripts/health_check.sh >> /root/singbox-eps-node/logs/health_check.log 2>&1
# ============================================================

BASE_DIR="/root/singbox-eps-node"
LOG_DIR="$BASE_DIR/logs"
LOG_FILE="$LOG_DIR/health_check.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# 告警阈值（v4.10.20 新增）
ESTAB_WARN=1500     # estab 连接数告警阈值（JP 实测 605，预留 2.5x 余量）
ESTAB_CRIT=3000     # estab 连接数严重告警
MEM_LOW=80          # 可用内存告警（MB）
SINGBOX_RSS_MAX=120 # sing-box RSS 上限（MB）
DISK_WARN=80        # 磁盘告警 %
DISK_CRIT=90        # 磁盘严重告警 %

mkdir -p "$LOG_DIR"

log() {
    echo "[$TIMESTAMP] $1" >> "$LOG_FILE"
}

log_section() {
    echo "[$TIMESTAMP] -- $1 --" >> "$LOG_FILE"
}

MEM_TOTAL=$(free -m | awk '/^Mem:/{print $2}')
MEM_AVAILABLE=$(free -m | awk '/^Mem:/{print $7}')
MEM_USED_PCT=$(( 100 - (MEM_AVAILABLE * 100 / MEM_TOTAL) ))

# ============================================================
# 0. 内存检查（最先执行）
# ============================================================
check_memory() {
    log_section "0. 内存检查"
    log "  系统内存: 总${MEM_TOTAL}MB | 可用${MEM_AVAILABLE}MB | 使用率${MEM_USED_PCT}%"

    if [ "$MEM_AVAILABLE" -lt "$MEM_LOW" ] || [ "$MEM_USED_PCT" -gt 80 ]; then
        log "  ⚠️  内存紧张，重启 cdn_monitor 释放内存"
        systemctl restart singbox-cdn
        sleep 5
        MEM_AFTER=$(free -m | awk '/^Mem:/{print $7}')
        if [ "$MEM_AFTER" -lt 120 ]; then
            log "  ⚠️  重启 cdn 后仍紧张(${MEM_AFTER}MB)，再重启 subscription_service"
            systemctl restart singbox-sub
            sleep 5
        fi
        log "  内存恢复: 可用$(free -m | awk '/^Mem:/{print $7}')MB"
    else
        log "  ✓  内存正常"
    fi

    SINGBOX_PID=$(pgrep -x sing-box)
    if [ -n "$SINGBOX_PID" ]; then
        SINGBOX_RSS=$(ps -o rss= -p "$SINGBOX_PID" 2>/dev/null || echo "0")
        SINGBOX_RSS_MB=$((SINGBOX_RSS / 1024))
        log "  sing-box RSS: ${SINGBOX_RSS_MB}MB"
        if [ "$SINGBOX_RSS_MB" -gt "$SINGBOX_RSS_MAX" ]; then
            log "  ⚠️  sing-box RSS 超阈值 (${SINGBOX_RSS_MB}MB > ${SINGBOX_RSS_MAX}MB)，重启"
            systemctl restart singbox
            sleep 3
        fi
    else
        log "  ❌ sing-box 进程不存在"
    fi
}

# ============================================================
# 1. config.json 自愈
# ============================================================
check_config_json() {
    log_section "1. config.json 自愈检查"
    if [ -f "$BASE_DIR/config.json" ]; then
        SIZE=$(stat -c%s "$BASE_DIR/config.json" 2>/dev/null || echo "0")
        log "  config.json 大小: ${SIZE} 字节"
        if [ "$SIZE" -gt 100 ]; then
            if python3 -c "import json; json.load(open('$BASE_DIR/config.json'))" 2>/dev/null; then
                log "  ✓  config.json 语法正常"
            else
                log "  ❌ config.json 语法损坏，重新生成"
                cd "$BASE_DIR" && python3 scripts/config_generator.py >> "$LOG_FILE" 2>&1
                systemctl restart singbox 2>/dev/null || true
            fi
        else
            log "  ❌ config.json 过小，可能损坏，重新生成"
            cd "$BASE_DIR" && python3 scripts/config_generator.py >> "$LOG_FILE" 2>&1
            systemctl restart singbox 2>/dev/null || true
        fi
    else
        log "  ❌ config.json 不存在，重新生成"
        cd "$BASE_DIR" && python3 scripts/config_generator.py >> "$LOG_FILE" 2>&1
        systemctl restart singbox 2>/dev/null || true
    fi
}

# ============================================================
# 2. 服务状态
# ============================================================
check_services() {
    log_section "2. 三服务状态"
    for svc in singbox singbox-sub singbox-cdn; do
        if systemctl is-active --quiet "$svc"; then
            log "  ✓  $svc: active"
        else
            log "  ❌ $svc 未运行，重启"
            systemctl restart "$svc"
            sleep 3
            if systemctl is-active --quiet "$svc"; then
                log "  ✓  $svc: 重启成功"
            else
                log "  ❌ $svc: 重启失败"
            fi
        fi
    done
}

# ============================================================
# 3. 端口监听
# ============================================================
check_ports() {
    log_section "3. 端口监听"
    # v4.14.0: 2053(HTTPUpgrade) 已下线，新增 2096(anyTLS)
    for port in 443 2087 8443 2083 2096; do
        if ss -tlnp 2>/dev/null | grep -q ":$port "; then
            log "  ✓  TCP $port 监听中"
        else
            log "  ❌ TCP $port 未监听"
        fi
    done
    # v4.14.0: TUIC 默认关闭，仅 ENABLE_TUIC=true 时检查
    if [ -f "$BASE_DIR/.env" ]; then
        enable_tuic_hc=$(grep "^ENABLE_TUIC=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 | tr '[:upper:]' '[:lower:]')
    fi
    if [ "$enable_tuic_hc" = "true" ]; then
        tuic_port_hc=$(grep "^TUIC_PORT=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2)
        if [ -n "$tuic_port_hc" ] && ss -ulnp 2>/dev/null | grep -q ":$tuic_port_hc "; then
            log "  ✓  UDP $tuic_port_hc (TUIC) 监听中"
        else
            log "  ❌ UDP $tuic_port_hc (TUIC) 未监听"
        fi
    else
        log "  ℹ️ TUIC v5 已关闭（ENABLE_TUIC=false）"
    fi
}

# ============================================================
# 4. estab 连接数告警（v4.10.20 新增）
# ============================================================
check_connections() {
    log_section "4. TCP 连接数监控"
    ESTAB=$(ss -tn state established 2>/dev/null | wc -l)
    ESTAB=$((ESTAB - 1))  # 减去 header 行
    log "  estab 连接数: $ESTAB"
    if [ "$ESTAB" -gt "$ESTAB_CRIT" ]; then
        log "  ❌ estab 连接数 $ESTAB 超过严重告警阈值 $ESTAB_CRIT！可能有连接泄漏或被攻击"
    elif [ "$ESTAB" -gt "$ESTAB_WARN" ]; then
        log "  ⚠️  estab 连接数 $ESTAB 超过告警阈值 $ESTAB_WARN"
    else
        log "  ✓  estab 连接数正常"
    fi

    # TIME_WAIT 监控
    TIMEWAIT=$(ss -tn state time-wait 2>/dev/null | wc -l)
    TIMEWAIT=$((TIMEWAIT - 1))
    log "  time_wait 连接数: $TIMEWAIT"
}

# ============================================================
# 5. 日志大小检查
# ============================================================
check_log_size() {
    log_section "5. 日志文件大小"
    for logfile in "$LOG_FILE" "/var/log/subscription_service.log" "/var/log/cdn_monitor.log" "/var/log/singbox.log"; do
        if [ -f "$logfile" ]; then
            SIZE=$(stat -c%s "$logfile" 2>/dev/null || echo "0")
            SIZE_MB=$((SIZE / 1024 / 1024))
            log "  $(basename $logfile): ${SIZE_MB}MB"
            if [ "$SIZE_MB" -gt 100 ]; then
                truncate -s 0 "$logfile"
                log "    ⚠️  超 100MB 已 truncate"
            fi
        fi
    done
    JOURNAL_SIZE=$(journalctl --disk-usage 2>/dev/null | grep -oP '\d+\.\d+' | head -1 || echo "0")
    JOURNAL_INT=$(echo "$JOURNAL_SIZE" | awk '{printf "%.0f", $1}')
    log "  journal 总大小: ${JOURNAL_SIZE}MB"
    if [ "$JOURNAL_INT" -gt 200 ]; then
        journalctl --vacuum-size=100M --vacuum-time=3d >/dev/null 2>&1
        log "    ⚠️  journal 超 200MB 已清理"
    fi
}

# ============================================================
# 6. 磁盘空间
# ============================================================
check_disk() {
    log_section "6. 磁盘空间"
    USAGE=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%')
    AVAIL=$(df -h / | tail -1 | awk '{print $4}')
    log "  根分区: 使用 ${USAGE}% | 可用 ${AVAIL}"
    if [ "$USAGE" -gt "$DISK_CRIT" ]; then
        log "  ❌ 磁盘严重不足: ${USAGE}%"
    elif [ "$USAGE" -gt "$DISK_WARN" ]; then
        log "  ⚠️  磁盘紧张: ${USAGE}%"
    else
        log "  ✓  磁盘正常"
    fi
}

# ============================================================
# 7. 数据库健康（v4.10.20 新增）
# ============================================================
check_database() {
    log_section "7. SQLite 数据库"
    DB="$BASE_DIR/data/singbox.db"
    if [ -f "$DB" ]; then
        DB_SIZE=$(stat -c%s "$DB" 2>/dev/null || echo "0")
        DB_SIZE_MB=$((DB_SIZE / 1024 / 1024))
        log "  singbox.db: ${DB_SIZE_MB}MB"

        # 检查 WAL 模式
        MODE=$(sqlite3 "$DB" "PRAGMA journal_mode;" 2>/dev/null)
        log "  journal_mode: $MODE"
        if [ "$MODE" != "wal" ]; then
            log "  ⚠️  非 WAL 模式，自动切换..."
            sqlite3 "$DB" "PRAGMA journal_mode = WAL;" 2>/dev/null
        fi

        # 检查 IP 数量
        IP_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM ip_performance" 2>/dev/null || echo "?")
        ACTIVE=$(sqlite3 "$DB" "SELECT COUNT(*) FROM ip_performance WHERE composite_score_v2 > 50" 2>/dev/null || echo "?")
        log "  ip_performance 总数: $IP_COUNT, 评分 > 50 的活跃 IP: $ACTIVE"
    else
        log "  ❌ singbox.db 不存在"
    fi
}

# ============================================================
# 8. 证书有效期（v4.10.20 新增）
# ============================================================
check_cert() {
    log_section "8. SSL 证书"
    CERT="$BASE_DIR/cert/fullchain.pem"
    if [ -f "$CERT" ]; then
        EXP=$(openssl x509 -in "$CERT" -noout -enddate 2>/dev/null | cut -d= -f2)
        EXP_TS=$(date -d "$EXP" +%s 2>/dev/null || echo "0")
        NOW_TS=$(date +%s)
        DAYS_LEFT=$(( (EXP_TS - NOW_TS) / 86400 ))
        log "  到期时间: $EXP (剩余 $DAYS_LEFT 天)"
        if [ "$DAYS_LEFT" -lt 30 ]; then
            log "  ⚠️  证书即将到期，请检查 cert_manager.py 续签任务"
        fi
    else
        log "  ❌ 证书文件不存在: $CERT"
    fi
}

# ============================================================
# 9. Cloudflare 代理入口规则自愈（v4.12.6 新增）
# ============================================================
check_cloudflare_proxy_rules() {
    log_section "9. Cloudflare 代理入口规则"
    if [ ! -f "$BASE_DIR/scripts/cloudflare_proxy_rules.py" ]; then
        log "  ⚠️  cloudflare_proxy_rules.py 不存在，跳过"
        return
    fi
    if ! grep -q '^CF_API_TOKEN=' "$BASE_DIR/.env" 2>/dev/null; then
        log "  ⚠️  CF_API_TOKEN 未配置，跳过 Cloudflare 规则自愈"
        return
    fi
    if cd "$BASE_DIR" && python3 scripts/cloudflare_proxy_rules.py apply >> "$LOG_FILE" 2>&1; then
        log "  ✓  Cloudflare 代理入口规则已确认"
    else
        log "  ❌ Cloudflare 代理入口规则修复失败，请检查 CF_API_TOKEN 权限"
    fi
}

# ============================================================
# 主流程
# ============================================================
log "===== 健康检查开始 ====="

check_memory
check_config_json
check_services
check_ports
check_connections
check_log_size
check_disk
check_database
check_cert
check_cloudflare_proxy_rules

log "===== 健康检查完成 ====="
log ""
