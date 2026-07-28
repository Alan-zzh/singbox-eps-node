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
DEPLOY_MODE_HC=$(grep '^DEPLOY_MODE=' "$BASE_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '\r')

# 告警阈值（v4.10.20 新增）
ESTAB_WARN=1500     # estab 连接数告警阈值（JP 实测 605，预留 2.5x 余量）
ESTAB_CRIT=3000     # estab 连接数严重告警
MEM_LOW=80          # 可用内存告警（MB）
SINGBOX_RSS_MAX=120 # sing-box RSS 上限（MB）
DISK_WARN=80        # 磁盘告警 %
DISK_CRIT=90        # 磁盘严重告警 %

mkdir -p "$LOG_DIR"
HEALTH_FAILED=0

log() {
    case "$1" in
        *"❌"*) HEALTH_FAILED=1 ;;
    esac
    echo "[$TIMESTAMP] $1" >> "$LOG_FILE"
}

log_section() {
    echo "[$TIMESTAMP] -- $1 --" >> "$LOG_FILE"
}

case "$DEPLOY_MODE_HC" in
    cdn|direct) ;;
    *)
        log "  ❌ DEPLOY_MODE 必须明确且只能为 cdn/direct，当前为 ${DEPLOY_MODE_HC:-缺失}"
        exit 1
        ;;
esac

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
        if [ "$DEPLOY_MODE_HC" = "direct" ]; then
            log "  ⚠️  内存紧张（direct 模式无 cdn_monitor），重启 subscription_service 释放内存"
            systemctl restart singbox-sub
            sleep 5
        else
            log "  ⚠️  内存紧张，重启 cdn_monitor 释放内存"
            systemctl restart singbox-cdn
            sleep 5
        fi
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
    services="singbox singbox-sub"
    if [ "$DEPLOY_MODE_HC" = "cdn" ]; then
        services="$services singbox-cdn"
    else
        systemctl stop singbox-cdn 2>/dev/null || true
        systemctl disable singbox-cdn 2>/dev/null || true
        log "  ⏭️  singbox-cdn: direct 模式已禁用"
    fi
    for svc in $services; do
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
    ports="443 2087 2096"
    if [ "$DEPLOY_MODE_HC" = "cdn" ]; then
        ports="$ports 8443 2083"
    fi
    for dynamic_key in TROJAN_TCP_PORT; do
        dynamic_port=$(grep "^${dynamic_key}=" "$BASE_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r')
        [ -n "$dynamic_port" ] && ports="$ports $dynamic_port"
    done
    enable_socks5_hc=$(grep '^ENABLE_SOCKS5=' "$BASE_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
    enable_socks5_hc=${enable_socks5_hc:-true}
    if [[ "$enable_socks5_hc" =~ ^(true|1|yes|on)$ ]]; then
        socks5_port_hc=$(grep '^SOCKS5_PORT=' "$BASE_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '\r')
        socks5_user_hc=$(grep '^SOCKS5_USER=' "$BASE_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r')
        socks5_pass_hc=$(grep '^SOCKS5_PASSWORD=' "$BASE_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r')
        if [ -n "$socks5_user_hc" ] && [ -n "$socks5_pass_hc" ]; then
            ports="$ports ${socks5_port_hc:-1080}"
        else
            log "  ❌ 本机认证 SOCKS5 已启用但凭据不完整"
        fi
    elif [[ "$enable_socks5_hc" =~ ^(false|0|no|off)$ ]]; then
        log "  ⏭️  本机认证 SOCKS5 已关闭"
    else
        log "  ❌ ENABLE_SOCKS5 配置非法"
    fi
    for port in $ports; do
        if ss -tlnp 2>/dev/null | grep -q ":$port "; then
            log "  ✓  TCP $port 监听中"
        else
            log "  ❌ TCP $port 未监听"
        fi
    done
    # v4.15.0: TUIC v5 加回，ENABLE_TUIC=true 默认开启
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

check_env_issues() {
    log_section "3b. .env 已知问题检测（v4.15.10 新增）"
    if [ ! -f "$BASE_DIR/.env" ]; then
        log "  ❌ .env 文件不存在"
        return
    fi
    
    # 1. REALITY_SHORT_ID 必须是有效 hex（禁止字面值 $(openssl...)，禁止 CRLF 污染）
    rs_val=$(grep "^REALITY_SHORT_ID=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 | tr -d "\"' \t\r\n")
    if [ -z "$rs_val" ]; then
        log "  ❌ REALITY_SHORT_ID 未设置"
    elif echo "$rs_val" | grep -qE '^[0-9a-f]{16}$'; then
        log "  ✓  REALITY_SHORT_ID 有效 hex"
    elif echo "$rs_val" | grep -qE '^[0-9a-f]{32}$'; then
        log "  ✓  REALITY_SHORT_ID 有效 hex(32)"
    else
        log "  ❌ REALITY_SHORT_ID 值异常: '$rs_val'（可能是字面值或 CRLF 污染）"
    fi
    
    # 2. CF_API_TOKEN 基本格式验证（警告级别，非阻塞）
    cf_token=$(grep "^CF_API_TOKEN=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2- | tr -d "'\" \t\r\n")
    if [ -n "$cf_token" ]; then
        if echo "$cf_token" | grep -qE '^[0-9a-f]{40}$'; then
            log "  ✓  CF_API_TOKEN 40-char hex"
        elif echo "$cf_token" | grep -qE '^cfat_'; then
            log "  ✓  CF_API_TOKEN cfat_ token (${#cf_token} chars)"
        elif [ ${#cf_token} -ge 30 ]; then
            log "  ✓  CF_API_TOKEN (${#cf_token} chars, user-confirmed)"
        else
            log "  ⚠️  CF_API_TOKEN 仅 ${#cf_token} 字符，可能过短"
        fi
    fi
    
    # 3. 固定香港直连节点必须是 direct 模式
    cf_dom=$(grep "^CF_DOMAIN=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 | tr -d '\r\n\t ')
    if echo "$cf_dom" | grep -qE '^(hk[12]|hkbeiyong)\.'; then
        dm=$(grep "^DEPLOY_MODE=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 | tr -d '\r\n\t ')
        if [ "$dm" != "direct" ]; then
            log "  ❌ 香港直连节点($cf_dom) 必须 direct 模式，当前: $dm"
        else
            log "  ✓  香港固定 direct 节点模式正确"
        fi
    fi
    
    # 4. .env 是否有 CRLF 换行（Windows 创建特征）
    if grep -rl $'\r$' "$BASE_DIR/.env" 2>/dev/null | grep -q .; then
        log "  ⚠️  .env 含 CRLF 换行（Windows 格式），建议 dos2unix 转换"
    fi
}

# ============================================================
# 3c. AI SOCKS5 业务检查（只记录脱敏汇总）
# ============================================================
reload_ai_socks_config() {
    (
        cd "$BASE_DIR" \
            && python3 scripts/config_generator.py >> "$LOG_FILE" 2>&1 \
            && /usr/local/bin/sing-box check -c "$BASE_DIR/config.json" >> "$LOG_FILE" 2>&1 \
            && systemctl restart singbox >> "$LOG_FILE" 2>&1 \
            && systemctl is-active --quiet singbox
    )
}

check_ai_socks5() {
    log_section "3c. AI SOCKS5 业务检查"
    local checker result rc routing marker transition reload_pending marker_tmp
    checker="$BASE_DIR/scripts/ai_socks5_health.py"
    marker="$BASE_DIR/data/ai_socks5_runtime_disabled"
    transition="${marker}.transition"
    reload_pending="${marker}.reload_pending"
    mkdir -p "$BASE_DIR/data"
    if [ ! -f "$checker" ]; then
        log "  ❌ AI SOCKS5 检查器缺失"
        return
    fi

    # 上次切换若在重载中被中断，先恢复到安全的 direct 回退态；下方健康检查会再次尝试恢复。
    if [ -f "$transition" ]; then
        mv -f -- "$transition" "$marker"
        chmod 600 "$marker"
        if reload_ai_socks_config; then
            rm -f -- "$reload_pending"
            log "  ⚠️  检测到未完成的 AI SOCKS5 切换，已恢复 direct 回退态"
        else
            : > "$reload_pending"
            chmod 600 "$reload_pending"
            log "  ❌ 未完成切换的 direct 回退配置重载失败，保留标记等待下次重试"
        fi
    fi

    result=$(python3 "$checker" --env "$BASE_DIR/.env" --json 2>&1)
    rc=$?
    routing=$(grep '^AI_SOCKS5_ROUTING=' "$BASE_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
    routing=${routing:-off}
    if [ "$rc" -eq 0 ]; then
        log "  ✓  AI SOCKS5: $result"
        if [ -f "$marker" ]; then
            mv -f -- "$marker" "$transition"
            if reload_ai_socks_config; then
                rm -f -- "$transition" "$reload_pending"
                log "  ✓  AI SOCKS5 已恢复并完成配置切换"
            else
                mv -f -- "$transition" "$marker"
                chmod 600 "$marker"
                if reload_ai_socks_config; then
                    rm -f -- "$reload_pending"
                else
                    : > "$reload_pending"
                    chmod 600 "$reload_pending"
                fi
                log "  ❌ AI SOCKS5 恢复配置重载失败，已回滚 direct 标记并等待下次重试"
            fi
        fi
    else
        log "  ❌ AI SOCKS5 路由已开启但业务检查失败: $result"
        if [ "$routing" = "on" ] && [ ! -f "$marker" ]; then
            marker_tmp="${marker}.$$"
            : > "$marker_tmp"
            chmod 600 "$marker_tmp"
            mv -f -- "$marker_tmp" "$marker"
            if reload_ai_socks_config; then
                rm -f -- "$reload_pending"
                log "  ⚠️  所有 AI SOCKS5 失效，已切换到 direct 回退态"
            else
                rm -f -- "$marker" "$reload_pending"
                reload_ai_socks_config || true
                log "  ❌ AI SOCKS5 direct 回退配置重载失败，已撤销标记并等待下次重试"
            fi
        elif [ "$routing" = "on" ] && [ -f "$marker" ] && [ -f "$reload_pending" ]; then
            if reload_ai_socks_config; then
                rm -f -- "$reload_pending"
                log "  ✓  AI SOCKS5 direct 回退配置重载重试成功"
            else
                log "  ❌ AI SOCKS5 direct 回退配置重载重试失败，保留待重试标记"
            fi
        fi
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
        DEPLOY_MODE_CERT=$(grep '^DEPLOY_MODE=' "$BASE_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '\r')
        CF_DOMAIN_CERT=$(grep '^CF_DOMAIN=' "$BASE_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "'\" \t\r")
        if [ -n "$CF_DOMAIN_CERT" ]; then
            if [ "$DEPLOY_MODE_CERT" = "cdn" ]; then
                CF_DOMAIN_CERT="sub-${CF_DOMAIN_CERT}"
            fi
            if printf '' | openssl s_client -connect 127.0.0.1:2087 -servername "$CF_DOMAIN_CERT" -verify_hostname "$CF_DOMAIN_CERT" -verify_return_error -CApath /etc/ssl/certs 2>&1 | grep -q 'Verify return code: 0'; then
                log "  ✓ 订阅证书已通过系统 CA 与域名校验"
            else
                log "  ❌ 订阅证书不可信，立即尝试 Let's Encrypt 修复"
                python3 "$BASE_DIR/scripts/cert_manager.py" --renew >> "$LOG_FILE" 2>&1 || true
                if ! printf '' | openssl s_client -connect 127.0.0.1:2087 -servername "$CF_DOMAIN_CERT" -verify_hostname "$CF_DOMAIN_CERT" -verify_return_error -CApath /etc/ssl/certs 2>&1 | grep -q 'Verify return code: 0'; then
                    log "  ❌ 订阅证书修复失败"
                fi
            fi
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
    if [ "$DEPLOY_MODE_HC" != "cdn" ]; then
        log "  ⏭️  direct 模式不得修改全域 CDN 代理/回源规则，跳过"
        return
    fi
    if [ ! -f "$BASE_DIR/scripts/cloudflare_proxy_rules.py" ]; then
        log "  ⚠️  cloudflare_proxy_rules.py 不存在，跳过"
        return
    fi
    if ! grep -q '^CF_API_TOKEN=' "$BASE_DIR/.env" 2>/dev/null; then
        log "  ⚠️  CF_API_TOKEN 未配置，跳过 Cloudflare 规则自愈"
        return
    fi
    local cf_domain_hc cf_zone_hc
    cf_domain_hc=$(grep '^CF_DOMAIN=' "$BASE_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r')
    cf_zone_hc=$(printf '%s' "$cf_domain_hc" | awk -F. 'NF>=2 {print $(NF-1)"."$NF}')
    if [ -z "$cf_domain_hc" ] || [ -z "$cf_zone_hc" ]; then
        log "  ❌ CF_DOMAIN 缺失或非法，无法自愈 CDN 规则"
        return
    fi
    if cd "$BASE_DIR" && python3 scripts/cloudflare_proxy_rules.py apply \
        --mode cdn --domain "$cf_domain_hc" --zone "$cf_zone_hc" >> "$LOG_FILE" 2>&1; then
        log "  ✓  Cloudflare 代理入口规则已确认"
    else
        log "  ❌ Cloudflare 代理入口规则修复失败，请检查 CF_API_TOKEN 权限"
    fi
}

# ============================================================
# 10. Cloudflare 全局安全设置巡检（v4.15.0 新增 P0）
# 确认 5 项关键设置，不符合时自动修复
# ============================================================
check_cloudflare_global_settings() {
    log_section "10. Cloudflare 全局安全设置"
    if [ ! -f "$BASE_DIR/scripts/cloudflare_proxy_rules.py" ]; then
        log "  ⚠️  cloudflare_proxy_rules.py 不存在，跳过"
        return
    fi
    if ! grep -q '^CF_API_TOKEN=' "$BASE_DIR/.env" 2>/dev/null; then
        log "  ⚠️  CF_API_TOKEN 未配置，跳过全局设置巡检"
        return
    fi
    # 通过 python3 -c 调用 cloudflare_proxy_rules.py 的 CloudflareClient
    # 检查 5 项设置：security_level / browser_check / bot_fight_mode / ssl / min_tls_version
    # 任一项不符合时自动修复（调用 set_zone_setting）
    cd "$BASE_DIR" && python3 -c "
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'scripts'))
from cloudflare_proxy_rules import CloudflareClient, load_env, ZONE_NAME

env = load_env()
if not env.get('CF_API_TOKEN'):
    print('  ⚠️  CF_API_TOKEN 未配置，跳过')
    sys.exit(0)

try:
    client = CloudflareClient(env)
    zone_id = client.get_zone_id(ZONE_NAME)
except Exception as e:
    print(f'  ❌ Cloudflare API 连接失败: {e}')
    sys.exit(1)

# 4 项标准设置（走 /zones/{zone_id}/settings/{setting} 端点）
# 格式: (setting_name, expected_value, fix_value)
standard_checks = [
    ('security_level', 'essentially_off', 'essentially_off'),
    ('browser_check', 'off', 'off'),
    ('ssl', 'full', 'full'),
    ('min_tls_version', '1.2', '1.2'),
]

issues = []
for setting, expected, fix_value in standard_checks:
    try:
        current = client.get_zone_setting(zone_id, setting)
        current_norm = str(current).strip().lower()
        expected_norm = str(expected).strip().lower()
        if current_norm != expected_norm:
            print(f'  ⚠️  {setting}: 当前={current} 目标={expected}，自动修复中...')
            try:
                client.set_zone_setting(zone_id, setting, fix_value)
                print(f'  ✓  {setting} 已修复为 {expected}')
            except Exception as e:
                issues.append(setting)
                print(f'  ❌ {setting} 修复失败: {e}')
        else:
            print(f'  ✓  {setting}: {current}')
    except Exception as e:
        issues.append(setting)
        print(f'  ❌ {setting} 检查失败: {e}')

# bot_fight_mode 走不同 API 端点（/bot_management/bot_fight_mode）
try:
    result = client.request('GET', f'/zones/{zone_id}/bot_management/bot_fight_mode')
    enabled = result.get('result', {}).get('enabled', False)
    if enabled:
        print(f'  ⚠️  bot_fight_mode: 当前=enabled 目标=disabled，自动修复中...')
        try:
            client.request('PUT', f'/zones/{zone_id}/bot_management/bot_fight_mode', {'enabled': False})
            print(f'  ✓  bot_fight_mode 已禁用')
        except Exception as e:
            issues.append('bot_fight_mode')
            print(f'  ❌ bot_fight_mode 修复失败: {e}')
    else:
        print(f'  ✓  bot_fight_mode: disabled')
except Exception as e:
    # 免费计划可能不支持 bot_management 端点，降级为提示
    print(f'  ℹ️  bot_fight_mode 检查跳过（API 不可用或计划不支持）: {e}')

if issues:
    print(f'  ❌ {len(issues)} 项设置修复失败: {issues}')
    sys.exit(1)
else:
    print(f'  ✓  CF 全局安全设置巡检完成（5 项全部正常）')
" >> "$LOG_FILE" 2>&1
    rc=$?
    if [ "$rc" -eq 0 ]; then
        log "  ✓  CF 全局安全设置巡检通过"
    else
        log "  ❌ CF 全局安全设置巡检有异常，详见上方日志"
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
check_env_issues
check_ai_socks5
check_connections
check_log_size
check_disk
check_database
check_cert
check_cloudflare_proxy_rules
check_cloudflare_global_settings

if [ "$HEALTH_FAILED" -ne 0 ]; then
    log "===== 健康检查完成（存在未恢复异常）====="
    log ""
    exit 1
fi

log "===== 健康检查完成（全部通过或已安全跳过）====="
log ""
exit 0
