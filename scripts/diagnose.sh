#!/bin/bash
# ============================================================
# singbox-eps-node 一键诊断脚本
# 版本: v1.0.85
# 日期: 2026-04-25
# 用途: 排查"连不上/掉线"问题，14项全面检查
# 部署: 放置在 /root/singbox-eps-node/scripts/diagnose.sh
# 用法: bash /root/singbox-eps-node/scripts/diagnose.sh
# ============================================================

BASE_DIR="/root/singbox-eps-node"
CERT_DIR="$BASE_DIR/cert"
DATA_DIR="$BASE_DIR/data"
ENV_FILE="$BASE_DIR/.env"
CONFIG_FILE="$BASE_DIR/config.json"
DB_FILE="$DATA_DIR/singbox.db"
LOG_FILE="/var/log/singbox.log"

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
FAIL_ITEMS=""
WARN_ITEMS=""

# ============================================================
# 状态记录函数
# ============================================================
mark_pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "  ✅ $1"
}

mark_fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    FAIL_ITEMS="$FAIL_ITEMS\n  ❌ $1 → 修复: $2"
    echo "  ❌ $1"
    echo "     修复建议: $2"
}

mark_warn() {
    WARN_COUNT=$((WARN_COUNT + 1))
    WARN_ITEMS="$WARN_ITEMS\n  ⚠️ $1"
    echo "  ⚠️ $1"
}

# ============================================================
# 1. 三个 systemd 服务运行状态
# ============================================================
check_services() {
    echo ""
    echo "=========================================="
    echo "【1/14】systemd 服务运行状态"
    echo "=========================================="

    for svc in singbox singbox-sub singbox-cdn; do
        STATUS=$(systemctl is-active "$svc" 2>/dev/null)
        if [ "$STATUS" = "active" ]; then
            mark_pass "$svc: 运行中 (active)"
        else
            mark_fail "$svc: 未运行 (状态=$STATUS)" "systemctl restart $svc && systemctl status $svc"
        fi
    done
}

# ============================================================
# 2. 所有端口监听状态
# ============================================================
check_port_listening() {
    echo ""
    echo "=========================================="
    echo "【2/14】端口监听状态"
    echo "=========================================="

    for port in 443 8443 2053 2083 2087; do
        if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
            mark_pass "TCP $port: 监听中"
        else
            mark_fail "TCP $port: 未监听" "检查 singbox 配置是否包含该端口入站，然后 systemctl restart singbox"
        fi
    done

    if ss -ulnp 2>/dev/null | grep -q ":443 "; then
        mark_pass "UDP 443: 监听中 (Hysteria2)"
    else
        mark_fail "UDP 443: 未监听" "检查 singbox 配置中 Hysteria2 入站是否启用，然后 systemctl restart singbox"
    fi
}

# ============================================================
# 3. SSL 证书有效期和文件完整性
# ============================================================
check_ssl_cert() {
    echo ""
    echo "=========================================="
    echo "【3/14】SSL 证书有效期和文件完整性"
    echo "=========================================="

    if [ ! -d "$CERT_DIR" ]; then
        mark_fail "证书目录不存在: $CERT_DIR" "运行 cert_manager.py 生成证书，或检查 install.sh 是否正确安装"
        return
    fi

    for f in fullchain.pem cert.pem key.pem; do
        if [ -f "$CERT_DIR/$f" ]; then
            SIZE=$(stat -c%s "$CERT_DIR/$f" 2>/dev/null || stat -f%z "$CERT_DIR/$f" 2>/dev/null)
            if [ "$SIZE" -gt 0 ]; then
                mark_pass "$f: 存在 (${SIZE}字节)"
            else
                mark_fail "$f: 文件为空" "重新生成证书: python3 $BASE_DIR/scripts/cert_manager.py"
            fi
        else
            mark_warn "$f: 不存在"
        fi
    done

    CERT_FILE=""
    for f in "$CERT_DIR/fullchain.pem" "$CERT_DIR/cert.pem"; do
        if [ -f "$f" ] && [ -s "$f" ]; then
            CERT_FILE="$f"
            break
        fi
    done

    if [ -n "$CERT_FILE" ]; then
        EXPIRY=$(openssl x509 -enddate -noout -in "$CERT_FILE" 2>/dev/null | cut -d= -f2)
        if [ -n "$EXPIRY" ]; then
            EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s 2>/dev/null)
            NOW_EPOCH=$(date +%s)
            DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
            if [ "$DAYS_LEFT" -gt 30 ]; then
                mark_pass "证书有效期: 剩余${DAYS_LEFT}天 (到期: $EXPIRY)"
            elif [ "$DAYS_LEFT" -gt 7 ]; then
                mark_warn "证书有效期: 剩余${DAYS_LEFT}天，即将过期 (到期: $EXPIRY)"
            elif [ "$DAYS_LEFT" -gt 0 ]; then
                mark_fail "证书有效期: 仅剩${DAYS_LEFT}天！ (到期: $EXPIRY)" "立即续签: python3 $BASE_DIR/scripts/cert_manager.py --renew"
            else
                mark_fail "证书已过期！ (到期: $EXPIRY)" "立即续签: python3 $BASE_DIR/scripts/cert_manager.py --renew"
            fi
        else
            mark_fail "无法解析证书有效期" "证书文件可能损坏，重新生成: python3 $BASE_DIR/scripts/cert_manager.py"
        fi
    fi
}

# ============================================================
# 4. iptables 端口跳跃规则
# ============================================================
check_port_hopping() {
    echo ""
    echo "=========================================="
    echo "【4/14】iptables 端口跳跃规则 (21000-21200→443)"
    echo "=========================================="

    UDP_FIRST=$(iptables -t nat -L PREROUTING -n 2>/dev/null | grep -c "DNAT.*udp.*dpt:21000.*to:.*:443")
    UDP_LAST=$(iptables -t nat -L PREROUTING -n 2>/dev/null | grep -c "DNAT.*udp.*dpt:21200.*to:.*:443")
    TCP_FIRST=$(iptables -t nat -L PREROUTING -n 2>/dev/null | grep -c "DNAT.*tcp.*dpt:21000.*to:.*:443")
    TCP_LAST=$(iptables -t nat -L PREROUTING -n 2>/dev/null | grep -c "DNAT.*tcp.*dpt:21200.*to:.*:443")

    if [ "$UDP_FIRST" -ge 1 ] && [ "$UDP_LAST" -ge 1 ]; then
        mark_pass "UDP端口跳跃规则: 存在 (21000→443, 21200→443)"
    else
        mark_fail "UDP端口跳跃规则: 缺失或不完整 (首端口21000匹配=$UDP_FIRST, 尾端口21200匹配=$UDP_LAST)" "运行 cert_manager.py 重新生成规则，或手动添加: iptables -t nat -A PREROUTING -p udp --dport 21000:21200 -j DNAT --to-destination :443"
    fi

    if [ "$TCP_FIRST" -ge 1 ] && [ "$TCP_LAST" -ge 1 ]; then
        mark_pass "TCP端口跳跃规则: 存在 (21000→443, 21200→443)"
    else
        mark_fail "TCP端口跳跃规则: 缺失或不完整 (首端口21000匹配=$TCP_FIRST, 尾端口21200匹配=$TCP_LAST)" "HY2必须UDP+TCP双规则！运行 cert_manager.py 或手动添加: iptables -t nat -A PREROUTING -p tcp --dport 21000:21200 -j DNAT --to-destination :443"
    fi
}

# ============================================================
# 5. 防火墙默认策略
# ============================================================
check_firewall_policy() {
    echo ""
    echo "=========================================="
    echo "【5/14】防火墙默认策略"
    echo "=========================================="

    POLICY=$(iptables -L INPUT -n 2>/dev/null | head -1 | grep -o 'policy [A-Z]*' | awk '{print $2}')
    if [ "$POLICY" = "ACCEPT" ]; then
        mark_pass "INPUT默认策略: ACCEPT (全放行)"
    else
        mark_fail "INPUT默认策略: $POLICY (应为ACCEPT)" "iptables -P INPUT ACCEPT && iptables -F INPUT && netfilter-persistent save"
    fi
}

# ============================================================
# 6. CDN 优选IP数据库
# ============================================================
check_cdn_database() {
    echo ""
    echo "=========================================="
    echo "【6/14】CDN 优选IP数据库"
    echo "=========================================="

    if [ ! -f "$DB_FILE" ]; then
        mark_fail "数据库文件不存在: $DB_FILE" "检查 install.sh 是否正确初始化数据库"
        return
    fi

    if ! command -v sqlite3 &>/dev/null; then
        mark_warn "sqlite3 命令不可用，无法读取数据库"
        return
    fi

    TABLE_EXISTS=$(sqlite3 "$DB_FILE" "SELECT name FROM sqlite_master WHERE type='table' AND name='cdn_settings';" 2>/dev/null)
    if [ -z "$TABLE_EXISTS" ]; then
        mark_fail "cdn_settings 表不存在" "数据库初始化异常，检查 install.sh"
        return
    fi

    CDN_IPS=$(sqlite3 "$DB_FILE" "SELECT key || '=' || value FROM cdn_settings WHERE key LIKE '%cdn_ip%';" 2>/dev/null)
    CDN_UPDATE=$(sqlite3 "$DB_FILE" "SELECT value FROM cdn_settings WHERE key='cdn_updated_at';" 2>/dev/null)

    if [ -n "$CDN_IPS" ]; then
        mark_pass "CDN优选IP: $(echo "$CDN_IPS" | tr '\n' ', ' | sed 's/,$//')"
    else
        mark_fail "CDN优选IP: 数据库为空" "手动触发更新: systemctl restart singbox-cdn"
    fi

    if [ -n "$CDN_UPDATE" ]; then
        UPDATE_EPOCH=$(date -d "$CDN_UPDATE" +%s 2>/dev/null)
        NOW_EPOCH=$(date +%s)
        HOURS_AGO=$(( (NOW_EPOCH - UPDATE_EPOCH) / 3600 ))
        if [ "$HOURS_AGO" -le 2 ]; then
            mark_pass "CDN更新时间: $CDN_UPDATE (${HOURS_AGO}小时前)"
        else
            mark_warn "CDN更新时间: $CDN_UPDATE (已${HOURS_AGO}小时未更新，可能singbox-cdn卡住)"
        fi
    else
        mark_warn "CDN更新时间: 无法读取"
    fi
}

# ============================================================
# 7. singbox config.json 语法校验
# ============================================================
check_config_syntax() {
    echo ""
    echo "=========================================="
    echo "【7/14】singbox config.json 语法校验"
    echo "=========================================="

    if [ ! -f "$CONFIG_FILE" ]; then
        mark_fail "config.json 不存在: $CONFIG_FILE" "运行 config_generator.py 重新生成: python3 $BASE_DIR/scripts/config_generator.py"
        return
    fi

    RESULT=$(python3 -c "import json; json.load(open('$CONFIG_FILE'))" 2>&1)
    if [ $? -eq 0 ]; then
        mark_pass "config.json 语法: 正确"
    else
        mark_fail "config.json 语法错误: $RESULT" "检查 config.json 手动修改是否破坏了JSON格式，或重新生成: python3 $BASE_DIR/scripts/config_generator.py"
    fi
}

# ============================================================
# 8. .env 关键变量非空检查
# ============================================================
check_env_variables() {
    echo ""
    echo "=========================================="
    echo "【8/14】.env 关键变量非空检查"
    echo "=========================================="

    if [ ! -f "$ENV_FILE" ]; then
        mark_fail ".env 文件不存在: $ENV_FILE" "从 .env.example 复制并填写: cp $BASE_DIR/.env.example $ENV_FILE"
        return
    fi

    REQUIRED_VARS="SERVER_IP CF_DOMAIN VLESS_UUID VLESS_WS_UUID TROJAN_PASSWORD HYSTERIA2_PASSWORD REALITY_PRIVATE_KEY REALITY_PUBLIC_KEY"

    for var in $REQUIRED_VARS; do
        VAL=$(grep "^${var}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | xargs)
        if [ -n "$VAL" ]; then
            mark_pass "$var: 已设置"
        else
            mark_fail "$var: 未设置或为空" "编辑 $ENV_FILE 填写 $var 的值"
        fi
    done
}

# ============================================================
# 9. 系统资源
# ============================================================
check_system_resources() {
    echo ""
    echo "=========================================="
    echo "【9/14】系统资源"
    echo "=========================================="

    DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%')
    if [ "$DISK_USAGE" -lt 80 ]; then
        mark_pass "磁盘使用: ${DISK_USAGE}%"
    elif [ "$DISK_USAGE" -lt 90 ]; then
        mark_warn "磁盘使用: ${DISK_USAGE}%，需要清理"
    else
        mark_fail "磁盘使用: ${DISK_USAGE}%，严重不足！" "清理日志和临时文件: rm -f $BASE_DIR/logs/*.log.* && journalctl --vacuum-size=50M"
    fi

    MEM_TOTAL=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
    MEM_USED=$(free -m 2>/dev/null | awk '/^Mem:/{print $3}')
    if [ -n "$MEM_TOTAL" ] && [ "$MEM_TOTAL" -gt 0 ]; then
        MEM_PCT=$((MEM_USED * 100 / MEM_TOTAL))
        if [ "$MEM_PCT" -lt 80 ]; then
            mark_pass "内存使用: ${MEM_USED}M/${MEM_TOTAL}M (${MEM_PCT}%)"
        elif [ "$MEM_PCT" -lt 90 ]; then
            mark_warn "内存使用: ${MEM_USED}M/${MEM_TOTAL}M (${MEM_PCT}%)，偏高"
        else
            mark_fail "内存使用: ${MEM_USED}M/${MEM_TOTAL}M (${MEM_PCT}%)，严重不足！" "检查占用进程: ps aux --sort=-%mem | head -10"
        fi
    else
        mark_warn "无法读取内存信息"
    fi
}

# ============================================================
# 10. singbox 日志 ERROR/FATAL
# ============================================================
check_singbox_logs() {
    echo ""
    echo "=========================================="
    echo "【10/14】singbox 日志 ERROR/FATAL (最近1小时)"
    echo "=========================================="

    if [ ! -f "$LOG_FILE" ]; then
        mark_warn "日志文件不存在: $LOG_FILE (可能使用 journalctl)"
        JOURNAL_ERRORS=$(journalctl -u singbox --since "1 hour ago" --no-pager 2>/dev/null | grep -ciE "ERROR|FATAL")
        if [ "$JOURNAL_ERRORS" -gt 0 ]; then
            mark_fail "journalctl 最近1小时发现 ${JOURNAL_ERRORS} 条 ERROR/FATAL" "查看详情: journalctl -u singbox --since '1 hour ago' | grep -E 'ERROR|FATAL'"
        else
            mark_pass "journalctl 最近1小时无 ERROR/FATAL"
        fi
        return
    fi

    ERROR_COUNT=$(awk -v cutoff="$(date -d '1 hour ago' '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')" '
        $0 ~ /^[0-9]{4}-[0-9]{2}-[0-9]{2}/ {
            ts = $1 " " $2
        }
        /ERROR|FATAL/ {
            if (ts >= cutoff) count++
        }
        END { print count+0 }
    ' "$LOG_FILE" 2>/dev/null)

    if [ "${ERROR_COUNT:-0}" -eq 0 ]; then
        mark_pass "最近1小时无 ERROR/FATAL 日志"
    else
        mark_fail "最近1小时发现 ${ERROR_COUNT} 条 ERROR/FATAL" "查看详情: grep -E 'ERROR|FATAL' $LOG_FILE | tail -20"
    fi
}

# ============================================================
# 11. DNS 解析测试
# ============================================================
check_dns_resolution() {
    echo ""
    echo "=========================================="
    echo "【11/14】DNS 解析测试"
    echo "=========================================="

    if ! command -v dig &>/dev/null; then
        mark_warn "dig 命令不可用，跳过DNS测试 (安装: apt install dnsutils)"
        return
    fi

    GOOGLE_RESULT=$(dig +short @8.8.8.8 google.com 2>/dev/null | head -1)
    if [ -n "$GOOGLE_RESULT" ]; then
        mark_pass "Google DNS (8.8.8.8): google.com → $GOOGLE_RESULT"
    else
        mark_fail "Google DNS (8.8.8.8): 无法解析 google.com" "检查服务器网络连接和DNS配置: cat /etc/resolv.conf"
    fi

    BAIDU_RESULT=$(dig +short @223.5.5.5 baidu.com 2>/dev/null | head -1)
    if [ -n "$BAIDU_RESULT" ]; then
        mark_pass "阿里DNS (223.5.5.5): baidu.com → $BAIDU_RESULT"
    else
        mark_fail "阿里DNS (223.5.5.5): 无法解析 baidu.com" "检查服务器网络连接和DNS配置: cat /etc/resolv.conf"
    fi
}

# ============================================================
# 12. crontab 定时任务
# ============================================================
check_crontab() {
    echo ""
    echo "=========================================="
    echo "【12/14】crontab 定时任务"
    echo "=========================================="

    CRON_LIST=$(crontab -l 2>/dev/null)

    if echo "$CRON_LIST" | grep -q "health_check.sh"; then
        CRON_LINE=$(echo "$CRON_LIST" | grep "health_check.sh" | head -1)
        mark_pass "health_check.sh 定时任务: $CRON_LINE"
    else
        mark_fail "health_check.sh 定时任务: 未配置" "添加: (crontab -l 2>/dev/null; echo '*/5 * * * * $BASE_DIR/scripts/health_check.sh >> $BASE_DIR/logs/health_check.log 2>&1') | crontab -"
    fi

    if echo "$CRON_LIST" | grep -q "singbox-cdn"; then
        CRON_LINE=$(echo "$CRON_LIST" | grep "singbox-cdn" | head -1)
        mark_pass "singbox-cdn 重启定时任务: $CRON_LINE"
    else
        mark_fail "singbox-cdn 重启定时任务: 未配置 (CDN更新服务可能卡住)" "添加: (crontab -l 2>/dev/null; echo '0 * * * * systemctl restart singbox-cdn') | crontab -"
    fi
}

# ============================================================
# 13. BBR/FQ/CAKE qdisc 状态
# ============================================================
check_bbr_qdisc() {
    echo ""
    echo "=========================================="
    echo "【13/14】BBR/FQ/CAKE qdisc 状态"
    echo "=========================================="

    CC=$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null)
    if [ "$CC" = "bbr" ]; then
        mark_pass "TCP拥塞控制: BBR"
    else
        mark_fail "TCP拥塞控制: ${CC:-未设置} (应为bbr)" "启用BBR: sysctl -w net.ipv4.tcp_congestion_control=bbr && echo 'net.ipv4.tcp_congestion_control=bbr' >> /etc/sysctl.conf"
    fi

    QDISC=$(sysctl -n net.core.default_qdisc 2>/dev/null)
    if [ "$QDISC" = "cake" ] || [ "$QDISC" = "fq" ] || [ "$QDISC" = "fq_pie" ]; then
        mark_pass "默认队列规则: $QDISC"
    else
        mark_warn "默认队列规则: ${QDISC:-未设置} (推荐cake/fq_pie/fq)"
    fi

    MAIN_IF=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1)
    if [ -n "$MAIN_IF" ]; then
        TC_QDISC=$(tc qdisc show dev "$MAIN_IF" 2>/dev/null | head -2)
        if echo "$TC_QDISC" | grep -qi "cake"; then
            mark_pass "网卡 $MAIN_IF qdisc: CAKE"
        elif echo "$TC_QDISC" | grep -qi "fq_pie"; then
            mark_pass "网卡 $MAIN_IF qdisc: FQ-PIE (CAKE降级方案)"
        elif echo "$TC_QDISC" | grep -qi "fq"; then
            mark_warn "网卡 $MAIN_IF qdisc: FQ (可用，但cake/fq_pie更优)"
        else
            mark_warn "网卡 $MAIN_IF qdisc: $TC_QDISC"
        fi
    else
        mark_warn "无法检测主网卡接口"
    fi
}

# ============================================================
# 14. 订阅接口可达性
# ============================================================
check_subscription_access() {
    echo ""
    echo "=========================================="
    echo "【14/14】订阅接口可达性"
    echo "=========================================="

    COUNTRY=$(grep "^COUNTRY_CODE=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 || echo "US")
    SUB_URL="https://localhost:2087/sub/${COUNTRY}"

    HTTP_CODE=$(curl -sk --connect-timeout 5 -o /dev/null -w "%{http_code}" "$SUB_URL" 2>/dev/null)
    if [ "$HTTP_CODE" = "200" ]; then
        mark_pass "订阅接口(localhost): HTTP $HTTP_CODE"
    elif [ "$HTTP_CODE" = "000" ]; then
        mark_fail "订阅接口(localhost): 连接被拒绝" "检查 singbox-sub 是否运行: systemctl status singbox-sub"
    else
        mark_warn "订阅接口(localhost): HTTP $HTTP_CODE (期望200)"
    fi

    CF_DOMAIN=$(grep "^CF_DOMAIN=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | xargs)
    if [ -n "$CF_DOMAIN" ]; then
        DOMAIN_URL="https://${CF_DOMAIN}:2087/sub/${COUNTRY}"
        DOMAIN_CODE=$(curl -s --connect-timeout 5 -o /dev/null -w "%{http_code}" "$DOMAIN_URL" 2>/dev/null)
        CURL_EXIT=$?
        if [ "$DOMAIN_CODE" = "200" ]; then
            mark_pass "订阅接口(域名${CF_DOMAIN}): HTTP $DOMAIN_CODE，证书匹配"
        elif [ "$CURL_EXIT" -eq 60 ] || [ "$DOMAIN_CODE" = "000" ]; then
            mark_fail "订阅接口(域名${CF_DOMAIN}): SSL证书不匹配或无法连接" "检查证书是否颁发给 ${CF_DOMAIN}，重新生成证书: python3 $BASE_DIR/scripts/cert_manager.py"
        else
            mark_warn "订阅接口(域名${CF_DOMAIN}): HTTP $DOMAIN_CODE (可能CDN未配置或DNS未解析)"
        fi
    else
        mark_warn "CF_DOMAIN 未配置，跳过域名访问测试"
    fi
}

# ============================================================
# 汇总报告
# ============================================================
print_summary() {
    echo ""
    echo "=========================================="
    echo "  诊断汇总报告"
    echo "=========================================="
    TOTAL=$((PASS_COUNT + FAIL_COUNT + WARN_COUNT))
    echo ""
    echo "  总检查项数: $TOTAL"
    echo "  ✅ 通过: $PASS_COUNT"
    echo "  ❌ 失败: $FAIL_COUNT"
    echo "  ⚠️ 警告: $WARN_COUNT"
    echo ""

    if [ "$FAIL_COUNT" -gt 0 ]; then
        echo "  ── 失败项及修复建议 ──"
        echo -e "$FAIL_ITEMS"
        echo ""
    fi

    if [ "$WARN_COUNT" -gt 0 ]; then
        echo "  ── 警告项 ──"
        echo -e "$WARN_ITEMS"
        echo ""
    fi

    if [ "$FAIL_COUNT" -eq 0 ] && [ "$WARN_COUNT" -eq 0 ]; then
        echo "  🎉 所有检查项均通过，系统状态正常！"
    elif [ "$FAIL_COUNT" -eq 0 ]; then
        echo "  💡 无失败项，但有警告项需要关注。"
    else
        echo "  🔧 存在 $FAIL_COUNT 个失败项，请按修复建议处理。"
    fi
    echo ""
    echo "=========================================="
}

# ============================================================
# 主流程
# ============================================================
echo "=========================================="
echo "  singbox-eps-node 一键诊断"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  服务器: $(hostname)"
echo "  内核: $(uname -r)"
echo "=========================================="

check_services
check_port_listening
check_ssl_cert
check_port_hopping
check_firewall_policy
check_cdn_database
check_config_syntax
check_env_variables
check_system_resources
check_singbox_logs
check_dns_resolution
check_crontab
check_bbr_qdisc
check_subscription_access

print_summary
