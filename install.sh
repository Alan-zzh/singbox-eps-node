#!/bin/bash
# ============================================================
# Singbox EPS Node 一键安装脚本
# 版本: v2.0.0
# 用途: 新VPS全自动部署（含系统优化+CDN优选+流量统计）
# 使用: bash <(curl -sL https://raw.githubusercontent.com/Alan-zzh/singbox-eps-node/main/install.sh)
#
# 【自动化功能清单】
# 阶段1-系统准备（全自动，无需用户操作）：
#   1. 系统更新：apt upgrade + 语言包 + 时区
#   2. 安装依赖：curl/wget/python3/openssl/sqlite3等
#   3. BBR+FQ+CAKE三合一加速（即时生效，无需重启）
#   4. 系统优化：文件描述符+内核参数
# 阶段2-部署服务（交互式配置）：
#   5. 卸载旧面板 → 安装singbox → 部署项目
#   6. 交互式配置：AI代理+域名
#   7. 生成配置+证书+防火墙+端口跳跃
#   8. 启动服务+验证
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

BASE_DIR="/root/singbox-eps-node"
REPO_URL="https://github.com/Alan-zzh/singbox-eps-node"

CF_DEFAULT_DOMAIN="us.290372913.xyz"
CF_DEFAULT_API_TOKEN="73a1fd81dd0f5087d45572135d5bf783ab26a"

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${CYAN}>>> $1${NC}"; }

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "请使用root用户运行此脚本"
        exit 1
    fi
}

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    else
        OS="unknown"
    fi
    if [[ "$OS" != "ubuntu" && "$OS" != "debian" ]]; then
        log_warn "此脚本针对Ubuntu/Debian优化，当前系统: $OS"
        log_warn "继续安装可能需要手动调整部分配置"
    fi
}

update_system() {
    log_step "【阶段1-步骤1/4】更新系统+安装语言包..."
    log_info "更新软件源..."
    apt-get update -y
    log_info "升级系统已安装的包..."
    DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
    log_info "安装语言包和基础工具..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        locales language-pack-en-base language-pack-zh-hans \
        sudo gnupg2 ca-certificates lsb-release
    locale-gen en_US.UTF-8 2>/dev/null || true
    update-locale LANG=en_US.UTF-8 2>/dev/null || true
    timedatectl set-timezone Asia/Shanghai 2>/dev/null || true
    log_info "系统更新完成（apt upgrade + 语言包 + 时区）"
}

install_dependencies() {
    log_step "【阶段1-步骤2/4】安装运行依赖..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        curl wget unzip python3 python3-pip python3-venv \
        cron iptables-persistent sqlite3 dnsutils openssl \
        net-tools procps iproute2
    log_info "运行依赖安装完成"
}

uninstall_old_panels() {
    log_step "检查并卸载旧面板..."
    # ⚠️ S-UI彻底卸载：停止服务+删除服务文件+删除目录+杀残留进程
    # Bug #33教训：只stop/disable不够，S-UI的cdn_monitor进程会自动重启
    for panel in s-ui x-ui marzban 3x-ui js-ui jsui; do
        if systemctl is-active --quiet "$panel" 2>/dev/null; then
            log_warn "检测到 $panel 正在运行，正在卸载..."
            systemctl stop "$panel" 2>/dev/null || true
            systemctl disable "$panel" 2>/dev/null || true
        fi
        # 清理所有相关systemd服务文件
        rm -f /etc/systemd/system/"$panel".service
        rm -f /etc/systemd/system/"$panel"-cdn.service
        rm -f /etc/systemd/system/"$panel"-cdn-monitor.service
        rm -f /etc/systemd/system/"$panel"-sub.service
        rm -f /etc/systemd/system/multi-user.target.wants/"$panel".service
        rm -f /etc/systemd/system/multi-user.target.wants/"$panel"-cdn-monitor.service
    done
    # S-UI/JSUI特殊处理：删除安装目录和残留进程
    # Bug #33教训：只stop/disable不够，S-UI的cdn_monitor进程会自动重启
    # JSUI也可能有残留进程在/opt/js-ui-manager或/usr/local/js-ui
    rm -rf /opt/s-ui-manager /usr/local/s-ui /opt/js-ui-manager /usr/local/js-ui
    pkill -f '/opt/s-ui-manager' 2>/dev/null || true
    pkill -f '/usr/local/s-ui' 2>/dev/null || true
    pkill -f '/opt/js-ui-manager' 2>/dev/null || true
    pkill -f '/usr/local/js-ui' 2>/dev/null || true
    pkill -f 'cdn_monitor.py.*s-ui' 2>/dev/null || true
    systemctl daemon-reload
    log_info "旧面板卸载完成"
}

set_default_qdisc_cake() {
    if grep -q "^net.core.default_qdisc=" /etc/sysctl.conf 2>/dev/null; then
        sed -i 's|^net.core.default_qdisc=.*|net.core.default_qdisc=cake|' /etc/sysctl.conf
    else
        echo "net.core.default_qdisc=cake" >> /etc/sysctl.conf
    fi
}

set_default_qdisc_fq_pie() {
    if grep -q "^net.core.default_qdisc=" /etc/sysctl.conf 2>/dev/null; then
        sed -i 's|^net.core.default_qdisc=.*|net.core.default_qdisc=fq_pie|' /etc/sysctl.conf
    else
        echo "net.core.default_qdisc=fq_pie" >> /etc/sysctl.conf
    fi
}

setup_fq_pie_qdisc() {
    local iface="${1:-$(ip route show default 2>/dev/null | awk '{print $5}' | head -1)}"
    iface=${iface:-eth0}

    set_default_qdisc_fq_pie

    if ! command -v tc &>/dev/null; then
        log_warn "tc命令不可用，仅设置sysctl默认队列"
        return
    fi

    FQ_PIE_OK=false
    tc qdisc replace dev "$iface" root fq_pie 2>/dev/null && FQ_PIE_OK=true || true

    if [ "$FQ_PIE_OK" = true ]; then
        log_info "FQ-PIE队列已应用到 $iface（降级方案，仍可与BBR配合）"
    else
        log_warn "FQ-PIE应用失败，仅设置sysctl默认队列"
        return
    fi

    cat > /etc/systemd/system/fq-pie-qdisc.service << 'EOF'
[Unit]
Description=FQ-PIE Queue Discipline (CAKE降级方案)
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/sbin/tc qdisc replace dev %i root fq_pie
ExecStop=/sbin/tc qdisc del dev %i root 2>/dev/null || true

[Install]
WantedBy=multi-user.target
EOF

    ln -sf /etc/systemd/system/fq-pie-qdisc.service "/etc/systemd/system/fq-pie-qdisc@${iface}.service" 2>/dev/null || true

    systemctl daemon-reload 2>/dev/null || true
    systemctl enable "fq-pie-qdisc@${iface}" 2>/dev/null || true
    log_info "FQ-PIE持久化服务已创建（fq-pie-qdisc@$iface，重启自动恢复）"
}

optimize_system() {
    log_step "【阶段1-步骤3/4】启用BBR+FQ+CAKE三合一网络加速..."

    if ! sysctl net.ipv4.tcp_congestion_control 2>/dev/null | grep -q "bbr"; then
        log_info "加速1/3：启用BBR（Google拥塞控制，不依赖丢包，主动探测带宽+RTT）..."
        grep -q "^net.ipv4.tcp_congestion_control=bbr" /etc/sysctl.conf 2>/dev/null || echo "net.ipv4.tcp_congestion_control=bbr" >> /etc/sysctl.conf
    else
        log_info "加速1/3：BBR已启用，跳过"
    fi

    log_info "加速2/3：启用FQ公平队列（为每个TCP连接独立缓冲，BBR的pacing依赖FQ）..."
    set_default_qdisc_cake

    log_info "加速3/3：启用CAKE队列管理（集成FQ+PIE，防止缓冲区膨胀，抗丢包）..."
    setup_cake_qdisc

    log_info "TCP调优（缓冲区+连接队列+保活+BBR高丢包参数）..."
    TCP_PARAMS="net.ipv4.tcp_fastopen=3
net.ipv4.tcp_tw_reuse=1
net.ipv4.ip_local_port_range=1024 65535
net.ipv4.tcp_max_syn_backlog=65536
net.core.somaxconn=65536
net.core.netdev_max_backlog=65536
net.ipv4.tcp_rmem=4096 87380 67108864
net.ipv4.tcp_wmem=4096 65536 67108864
net.ipv4.tcp_mtu_probing=1
net.ipv4.tcp_keepalive_time=600
net.ipv4.tcp_keepalive_intvl=30
net.ipv4.tcp_keepalive_probes=10
net.ipv4.tcp_slow_start_after_idle=0
net.ipv4.tcp_bbr_min_rtt_win_sec=60"
    echo "$TCP_PARAMS" | while IFS='=' read -r key value; do
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs)
        if [ -n "$key" ] && [ -n "$value" ]; then
            if grep -q "^${key}=" /etc/sysctl.conf 2>/dev/null; then
                sed -i "s|^${key}=.*|${key}=${value}|" /etc/sysctl.conf
            else
                echo "${key}=${value}" >> /etc/sysctl.conf
            fi
        fi
    done

    sysctl -p 2>/dev/null || true
    log_info "BBR+FQ+CAKE三合一加速已启用（即时生效，无需重启）"

    if ! grep -q "65535" /etc/security/limits.conf 2>/dev/null; then
        log_info "【阶段1-步骤4/4】提升文件描述符限制到65535..."
        cat >> /etc/security/limits.conf << 'EOF'
* soft nofile 65535
* hard nofile 65535
root soft nofile 65535
root hard nofile 65535
EOF
    fi

    log_info "阶段1完成：系统更新+依赖+BBR+FQ+CAKE三合一+优化（全部即时生效，无需重启）"
}

setup_cake_qdisc() {
    MAIN_IF=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1) || true
    MAIN_IF=${MAIN_IF:-eth0}
    CAKE_FAIL_REASON=""

    if ! command -v tc &>/dev/null; then
        log_info "安装iproute2（tc命令依赖）..."
        DEBIAN_FRONTEND=noninteractive apt-get install -y iproute2 2>/dev/null || true
    fi

    if ! command -v tc &>/dev/null; then
        log_warn "tc命令不可用，降级使用FQ-PIE"
        CAKE_FAIL_REASON="no_tc_command"
        setup_fq_pie_qdisc "$MAIN_IF"
        return
    fi

    CAKE_SUPPORTED=false
    if modprobe sch_cake 2>/dev/null; then
        CAKE_SUPPORTED=true
    elif tc qdisc add dev "$MAIN_IF" root handle 1: cake 2>/dev/null; then
        tc qdisc del dev "$MAIN_IF" root 2>/dev/null || true
        CAKE_SUPPORTED=true
    fi

    if [ "$CAKE_SUPPORTED" = false ]; then
        log_info "尝试安装CAKE内核模块（linux-modules-extra-$(uname -r)）..."
        DEBIAN_FRONTEND=noninteractive apt-get install -y "linux-modules-extra-$(uname -r)" 2>/dev/null || true
        if modprobe sch_cake 2>/dev/null; then
            CAKE_SUPPORTED=true
            CAKE_FAIL_REASON=""
            log_info "安装linux-modules-extra后CAKE模块可用"
        fi
    fi

    if [ "$CAKE_SUPPORTED" = false ]; then
        CAKE_FAIL_REASON="kernel_no_module"
        log_warn "内核不支持CAKE，降级使用FQ-PIE（仍可与BBR配合）"
        setup_fq_pie_qdisc "$MAIN_IF"
        return
    fi

    CAKE_OK=false
    tc qdisc replace dev "$MAIN_IF" root handle 1: cake bandwidth 1000mbit flowmode triple-isolate 2>/dev/null && CAKE_OK=true || true

    if [ "$CAKE_OK" = true ]; then
        log_info "CAKE队列已应用到 $MAIN_IF（flowmode=triple-isolate，带宽1000mbit）"
    else
        CAKE_FAIL_REASON="tc_apply_failed"
        log_warn "CAKE应用失败，降级使用FQ-PIE"
        setup_fq_pie_qdisc "$MAIN_IF"
        return
    fi

    cat > /etc/systemd/system/cake-qdisc.service << 'EOF'
[Unit]
Description=CAKE Queue Discipline (BBR+FQ+CAKE三合一加速)
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/sbin/tc qdisc replace dev %i root handle 1: cake bandwidth 1000mbit flowmode triple-isolate
ExecStop=/sbin/tc qdisc del dev %i root 2>/dev/null || true

[Install]
WantedBy=multi-user.target
EOF

    mkdir -p /etc/systemd/system/cake-qdisc.service.wants 2>/dev/null || true
    ln -sf /etc/systemd/system/cake-qdisc.service "/etc/systemd/system/cake-qdisc@${MAIN_IF}.service" 2>/dev/null || true

    systemctl daemon-reload 2>/dev/null || true
    systemctl enable "cake-qdisc@${MAIN_IF}" 2>/dev/null || true
    log_info "CAKE持久化服务已创建（cake-qdisc@$MAIN_IF，重启自动恢复）"
}

install_singbox() {
    log_step "安装 Singbox 内核..."
    if command -v singbox &>/dev/null; then
        CURRENT_VER=$(singbox version 2>/dev/null | head -1 || echo '未知版本')
        log_info "检测到 Singbox 已安装: $CURRENT_VER"
        echo ""
        echo -e "  ${YELLOW}Singbox 已安装，请选择操作：${NC}"
        echo -e "  1) 卸载重装（清除所有数据：配置/证书/流量记录/服务，全新安装）"
        echo -e "  2) 保留当前版本（默认，直接继续）"
        echo ""
        read -p "  请输入选择 [1/2]（默认2）: " SINGBOX_CHOICE
        SINGBOX_CHOICE=${SINGBOX_CHOICE:-2}

        if [ "$SINGBOX_CHOICE" = "1" ]; then
            log_info "卸载当前 Singbox 及所有关联数据（保留密码和密钥）..."
            PASSWORD_BACKUP="/tmp/singbox_passwords_backup.env"
            > "$PASSWORD_BACKUP"
            if [ -f "$BASE_DIR/.env" ]; then
                for FIELD in VLESS_UUID VLESS_WS_UUID TROJAN_PASSWORD HYSTERIA2_PASSWORD \
                             REALITY_PRIVATE_KEY REALITY_PUBLIC_KEY COUNTRY_CODE \
                             CF_DOMAIN CF_API_TOKEN AI_SOCKS5_SERVER AI_SOCKS5_PORT \
                             AI_SOCKS5_USER AI_SOCKS5_PASS SERVER_IP SUB_TOKEN TG_BOT_TOKEN \
                             TG_ADMIN_CHAT_ID; do
                    VALUE=$(grep "^${FIELD}=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
                    if [ -n "$VALUE" ]; then
                        echo "${FIELD}=${VALUE}" >> "$PASSWORD_BACKUP"
                    fi
                done
                log_info "密码和密钥已备份"
            fi
            systemctl stop singbox singbox-sub singbox-cdn 2>/dev/null || true
            systemctl disable singbox singbox-sub singbox-cdn 2>/dev/null || true
            rm -f /etc/systemd/system/singbox.service
            rm -f /etc/systemd/system/singbox-sub.service
            rm -f /etc/systemd/system/singbox-cdn.service
            systemctl daemon-reload 2>/dev/null || true
            rm -f /usr/local/bin/singbox
            if [ -d "$BASE_DIR" ]; then
                log_info "删除项目目录 $BASE_DIR（配置/证书/流量记录/日志全部清除）..."
                rm -rf "$BASE_DIR"
            fi
            crontab -l 2>/dev/null | grep -v "health_check.sh" | grep -v "cert_manager.py" | crontab - 2>/dev/null || true
            iptables -D INPUT -p udp --dport 21000:21199 -j ACCEPT 2>/dev/null || true
            iptables -D INPUT -p tcp --dport 21000:21199 -j ACCEPT 2>/dev/null || true
            netfilter-persistent save 2>/dev/null || true
            log_info "已完全卸载（二进制+配置+数据+证书+服务+定时任务+防火墙规则全部清除）"
            log_info "密码和密钥已备份，安装时将自动恢复"
            log_info "开始全新安装..."
        else
            log_info "保留当前 Singbox: $CURRENT_VER"
            return
        fi
    fi

    ARCH=$(uname -m)
    case $ARCH in
        x86_64)  SINGBOX_ARCH="amd64" ;;
        aarch64) SINGBOX_ARCH="arm64" ;;
        *)       log_error "不支持的架构: $ARCH"; exit 1 ;;
    esac

    SINGBOX_VER="1.13.9"
    SINGBOX_URL="https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VER}/sing-box-${SINGBOX_VER}-linux-${SINGBOX_ARCH}.tar.gz"
    log_info "下载 Singbox v${SINGBOX_VER} (${SINGBOX_ARCH})..."
    cd /tmp
    wget -q "$SINGBOX_URL" -O singbox.tar.gz
    tar -xzf singbox.tar.gz
    cp "sing-box-${SINGBOX_VER}-linux-${SINGBOX_ARCH}/sing-box" /usr/local/bin/sing-box
    chmod +x /usr/local/bin/sing-box
    ln -sf /usr/local/bin/sing-box /usr/local/bin/singbox
    rm -rf singbox.tar.gz "sing-box-${SINGBOX_VER}-linux-${SINGBOX_ARCH}"
    log_info "Singbox 安装完成: $(sing-box version | head -1)"
}

clone_repo() {
    log_step "部署项目文件..."
    if [ -d "$BASE_DIR" ]; then
        log_warn "$BASE_DIR 已存在，备份后重新部署..."
        mv "$BASE_DIR" "${BASE_DIR}.bak.$(date +%Y%m%d%H%M%S)"
    fi
    if command -v git &>/dev/null; then
        git clone "$REPO_URL" "$BASE_DIR"
    else
        apt-get install -y git
        git clone "$REPO_URL" "$BASE_DIR"
    fi
    mkdir -p "$BASE_DIR/logs" "$BASE_DIR/data" "$BASE_DIR/cert" "$BASE_DIR/backups"
    log_info "目录结构已创建（logs/data/cert/backups）"
}

setup_python_env() {
    log_step "配置Python环境..."
    cd "$BASE_DIR"
    pip3 install --quiet flask python-dotenv
    log_info "Python依赖已安装（flask + python-dotenv）"
}

generate_uuids_and_passwords() {
    log_step "生成协议密码和UUID..."
    PASSWORD_BACKUP="/tmp/singbox_passwords_backup.env"
    if [ -f "$PASSWORD_BACKUP" ]; then
        log_info "检测到密码备份，恢复旧密码（客户端无需重新配置）..."
        while IFS='=' read -r key value; do
            case "$key" in
                VLESS_UUID) VLESS_UUID="$value" ;;
                VLESS_WS_UUID) VLESS_WS_UUID="$value" ;;
                TROJAN_PASSWORD) TROJAN_PASSWORD="$value" ;;
                HYSTERIA2_PASSWORD) HYSTERIA2_PASSWORD="$value" ;;
                COUNTRY_CODE) COUNTRY_CODE="$value" ;;
            esac
        done < "$PASSWORD_BACKUP"
        log_info "密码已从备份恢复"
    fi
    VLESS_UUID=${VLESS_UUID:-$(python3 -c "import uuid; print(uuid.uuid4())")}
    VLESS_WS_UUID=${VLESS_WS_UUID:-$(python3 -c "import uuid; print(uuid.uuid4())")}
    TROJAN_PASSWORD=${TROJAN_PASSWORD:-$(python3 -c "import secrets; print(secrets.token_hex(16))")}
    HYSTERIA2_PASSWORD=${HYSTERIA2_PASSWORD:-$(python3 -c "import secrets; print(secrets.token_hex(16))")}
    SERVER_IP=$(curl -s --connect-timeout 5 https://api.ipify.org 2>/dev/null || echo "")
    if [ -n "$SERVER_IP" ]; then
        COUNTRY_CODE=$(curl -s --connect-timeout 5 "https://ipinfo.io/${SERVER_IP}/country" 2>/dev/null | tr -d '[:space:]' || echo "")
    fi
    COUNTRY_CODE=${COUNTRY_CODE:-US}
    log_info "服务器IP: ${SERVER_IP}，国家代码: ${COUNTRY_CODE}"
    log_info "UUID和密码已生成"
}

generate_reality_keys() {
    log_step "生成Reality密钥对..."
    PASSWORD_BACKUP="/tmp/singbox_passwords_backup.env"
    if [ -f "$PASSWORD_BACKUP" ]; then
        while IFS='=' read -r key value; do
            case "$key" in
                REALITY_PRIVATE_KEY) REALITY_PRIVATE_KEY="$value" ;;
                REALITY_PUBLIC_KEY) REALITY_PUBLIC_KEY="$value" ;;
            esac
        done < "$PASSWORD_BACKUP"
    fi
    if [ -z "$REALITY_PRIVATE_KEY" ] || [ -z "$REALITY_PUBLIC_KEY" ]; then
        REALITY_OUTPUT=$(singbox generate reality-keypair 2>/dev/null)
        REALITY_PRIVATE_KEY=$(echo "$REALITY_OUTPUT" | grep "PrivateKey" | awk '{print $2}')
        REALITY_PUBLIC_KEY=$(echo "$REALITY_OUTPUT" | grep "PublicKey" | awk '{print $2}')
    fi
    if [ -z "$REALITY_PRIVATE_KEY" ] || [ -z "$REALITY_PUBLIC_KEY" ]; then
        log_warn "自动生成失败，使用占位符，请手动配置"
        REALITY_PRIVATE_KEY="PLACEHOLDER_PRIVATE_KEY"
        REALITY_PUBLIC_KEY="PLACEHOLDER_PUBLIC_KEY"
    fi
    log_info "Reality密钥对已生成"
}

create_env_file() {
    log_step "创建.env配置文件..."
    SERVER_IP=$(curl -s --connect-timeout 5 https://api.ipify.org 2>/dev/null || echo "")
    AI_SOCKS5_SERVER=""
    AI_SOCKS5_PORT=""
    AI_SOCKS5_USER=""
    AI_SOCKS5_PASS=""
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  AI住宅代理配置（可选）${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  配置后，AI网站（ChatGPT/Claude/Gemini等）流量自动走SOCKS5代理"
    echo -e "  X/推特/groK不走代理，直连"
    echo -e "  如果没有代理节点，直接回车跳过即可"
    echo ""
    read -p "  是否配置AI住宅代理？(y/N): " SETUP_AI
    if [[ "$SETUP_AI" =~ ^[Yy]$ ]]; then
        read -p "  SOCKS5服务器地址: " AI_SOCKS5_SERVER
        read -p "  SOCKS5端口: " AI_SOCKS5_PORT
        read -p "  SOCKS5用户名: " AI_SOCKS5_USER
        read -p "  SOCKS5密码: " AI_SOCKS5_PASS
        if [ -n "$AI_SOCKS5_SERVER" ] && [ -n "$AI_SOCKS5_PORT" ]; then
            log_info "AI住宅代理已配置: ${AI_SOCKS5_SERVER}:${AI_SOCKS5_PORT}"
        else
            log_warn "SOCKS5地址或端口为空，跳过AI代理配置"
            AI_SOCKS5_SERVER=""
            AI_SOCKS5_PORT=""
            AI_SOCKS5_USER=""
            AI_SOCKS5_PASS=""
        fi
    else
        log_info "跳过AI住宅代理配置（后续可手动编辑.env）"
    fi
    CF_DOMAIN_INPUT="${CF_DEFAULT_DOMAIN}"
    CF_API_TOKEN_INPUT="${CF_DEFAULT_API_TOKEN}"
    if [ -f "$BASE_DIR/.env" ]; then
        OLD_CF_DOMAIN=$(grep "^CF_DOMAIN=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
        OLD_CF_TOKEN=$(grep "^CF_API_TOKEN=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
        [ -n "$OLD_CF_DOMAIN" ] && CF_DOMAIN_INPUT="$OLD_CF_DOMAIN"
        [ -n "$OLD_CF_TOKEN" ] && CF_API_TOKEN_INPUT="$OLD_CF_TOKEN"
    fi
    log_info "CF_DOMAIN: ${CF_DOMAIN_INPUT}"
    log_info "CF_API_TOKEN: ${CF_API_TOKEN_INPUT:0:8}..."
    cat > "$BASE_DIR/.env" << EOF
# Singbox EPS Node 环境变量配置
# 由安装脚本自动生成于 $(date '+%Y-%m-%d %H:%M:%S')

# ============ 必填 ============
SERVER_IP=${SERVER_IP}
CF_DOMAIN=${CF_DOMAIN_INPUT}

# ============ 协议密码 ============
VLESS_UUID=${VLESS_UUID}
VLESS_WS_UUID=${VLESS_WS_UUID}
TROJAN_PASSWORD=${TROJAN_PASSWORD}
HYSTERIA2_PASSWORD=${HYSTERIA2_PASSWORD}
REALITY_PRIVATE_KEY=${REALITY_PRIVATE_KEY}
REALITY_PUBLIC_KEY=${REALITY_PUBLIC_KEY}

# ============ 可选 ============
CF_API_TOKEN=${CF_API_TOKEN_INPUT}
COUNTRY_CODE=${COUNTRY_CODE}
SUB_TOKEN=
AI_SOCKS5_SERVER=${AI_SOCKS5_SERVER}
AI_SOCKS5_PORT=${AI_SOCKS5_PORT}
AI_SOCKS5_USER=${AI_SOCKS5_USER}
AI_SOCKS5_PASS=${AI_SOCKS5_PASS}
TG_BOT_TOKEN=
TG_ADMIN_CHAT_ID=
EOF
    chmod 600 "$BASE_DIR/.env"
    log_info ".env 已创建 (服务器IP: ${SERVER_IP:-未检测到，请手动填写})"
}

generate_config() {
    log_step "生成Singbox配置..."
    cd "$BASE_DIR"
    python3 scripts/config_generator.py
}

setup_certificate() {
    log_step "配置SSL证书..."
    cd "$BASE_DIR"
    python3 scripts/cert_manager.py --cf-cert || python3 scripts/cert_manager.py
}

setup_port_hopping() {
    log_step "设置Hysteria2端口跳跃规则 (21000-21200 → 443, UDP+TCP)..."
    cd "$BASE_DIR"
    python3 scripts/cert_manager.py --setup-iptables
}

create_systemd_services() {
    log_step "创建Systemd服务..."
    cat > /etc/systemd/system/singbox.service << EOF
[Unit]
Description=Singbox Proxy Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/singbox run -c ${BASE_DIR}/config.json
Restart=on-failure
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF
    cat > /etc/systemd/system/singbox-sub.service << EOF
[Unit]
Description=Singbox Subscription Service (含流量统计)
After=network.target singbox.service

[Service]
Type=simple
WorkingDirectory=${BASE_DIR}
ExecStart=/usr/bin/python3 ${BASE_DIR}/scripts/subscription_service.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    cat > /etc/systemd/system/singbox-cdn.service << EOF
[Unit]
Description=Singbox CDN Monitor Service (多源聚合评分排序)
After=network.target singbox.service

[Service]
Type=simple
WorkingDirectory=${BASE_DIR}
ExecStart=/usr/bin/python3 ${BASE_DIR}/scripts/cdn_monitor.py --daemon
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    log_info "Systemd服务已创建"
}

setup_firewall() {
    log_step "配置防火墙（默认全放行）..."
    iptables -P INPUT ACCEPT
    iptables -P FORWARD ACCEPT
    iptables -P OUTPUT ACCEPT
    iptables -F
    netfilter-persistent save 2>/dev/null || true
    log_info "防火墙已配置为全放行"
}

setup_health_check_cron() {
    log_step "配置定时任务..."
    (crontab -l 2>/dev/null | grep -v "health_check.sh"; echo "*/5 * * * * ${BASE_DIR}/scripts/health_check.sh >> ${BASE_DIR}/logs/health_check.log 2>&1") | crontab -
    (crontab -l 2>/dev/null | grep -v "cert_manager.py"; echo "0 3 1 * * /usr/bin/python3 ${BASE_DIR}/scripts/cert_manager.py --renew >> /var/log/singbox.log 2>&1") | crontab -
    # ⚠️ Bug #31教训：singbox-cdn的time.sleep(3600)会卡住，必须每小时重启一次
    # 守护进程模式虽然显示active但不再执行后续更新，crontab重启是兜底保障
    (crontab -l 2>/dev/null | grep -v "singbox-cdn"; echo "0 * * * * systemctl restart singbox-cdn >> ${BASE_DIR}/logs/cdn_restart.log 2>&1") | crontab -
    log_info "定时任务已配置（健康检查每5分钟 + CDN每小时重启 + 证书续签每月1号凌晨3点）"
}

setup_swap_and_optimize() {
    log_step "检查内存和Swap..."
    local total_mem=$(free -m | awk '/^Mem:/{print $2}')
    if [ "$total_mem" -lt 1024 ] && [ ! -f /swapfile ]; then
        log_info "内存 ${total_mem}MB < 1GB，创建2GB Swap..."
        dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
        sysctl vm.swappiness=10 >> /dev/null 2>&1 || true
        grep -q 'vm.swappiness' /etc/sysctl.conf && sed -i 's/vm.swappiness=.*/vm.swappiness=10/' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
        log_info "2GB Swap已创建并启用"
    elif [ -f /swapfile ]; then
        log_info "Swap已存在，跳过"
    else
        log_info "内存 ${total_mem}MB >= 1GB，无需Swap"
    fi
    systemctl stop fwupd.service 2>/dev/null || true
    systemctl disable fwupd.service 2>/dev/null || true
    systemctl mask fwupd.service 2>/dev/null || true
    if [ ! -f /etc/logrotate.d/singbox ]; then
        cat > /etc/logrotate.d/singbox << 'EOF'
/var/log/singbox.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    maxsize 50M
}
EOF
        log_info "singbox日志轮转已配置"
    fi
}

start_services() {
    log_step "启动所有服务..."
    if [ ! -f "${BASE_DIR}/config.json" ]; then
        log_error "config.json 不存在！重新生成..."
        cd "$BASE_DIR" && python3 scripts/config_generator.py
    fi
    if ! python3 -c "import json; json.load(open('${BASE_DIR}/config.json'))" 2>/dev/null; then
        log_error "config.json 语法错误！重新生成..."
        cd "$BASE_DIR" && python3 scripts/config_generator.py
    fi
    CERT_DIR_PATH="${BASE_DIR}/cert"
    if [ ! -f "${CERT_DIR_PATH}/cert.pem" ] && [ ! -f "${CERT_DIR_PATH}/fullchain.pem" ]; then
        log_warn "证书文件缺失，重新生成自签名证书..."
        cd "$BASE_DIR" && python3 scripts/cert_manager.py
    fi
    systemctl enable singbox singbox-sub singbox-cdn 2>/dev/null || true
    systemctl start singbox
    sleep 3
    if ! systemctl is-active --quiet singbox; then
        log_error "singbox 启动失败！诊断信息："
        journalctl -u singbox --no-pager -n 20 2>/dev/null || true
        echo ""
        log_warn "尝试检查config.json..."
        /usr/local/bin/singbox check -c "${BASE_DIR}/config.json" 2>&1 || true
        echo ""
        log_warn "singbox启动失败，但订阅服务仍可运行"
        log_warn "请检查上方错误信息，修复后运行: systemctl restart singbox"
    fi
    systemctl start singbox-sub
    sleep 2
    systemctl start singbox-cdn
    log_info "所有服务已启动"
}

verify_installation() {
    log_step "验证安装..."
    echo ""
    ALL_OK=true
    for svc in singbox singbox-sub singbox-cdn; do
        if systemctl is-active --quiet "$svc"; then
            echo -e "  ${GREEN}✅${NC} $svc: 运行中"
        else
            echo -e "  ${RED}❌${NC} $svc: 未运行"
            ALL_OK=false
        fi
    done
    echo ""
    echo -e "  端口监听:"
    for port in 443 8443 2053 2083 2087; do
        if ss -tlnp | grep -q ":$port "; then
            echo -e "    ${GREEN}✅${NC} 端口 $port: 监听中"
        else
            echo -e "    ${RED}❌${NC} 端口 $port: 未监听"
            ALL_OK=false
        fi
    done
    echo ""
    echo -e "  系统优化:"
    if sysctl net.ipv4.tcp_congestion_control 2>/dev/null | grep -q "bbr"; then
        echo -e "    ${GREEN}✅${NC} BBR加速: 已启用"
    else
        echo -e "    ${YELLOW}⚠️${NC} BBR加速: 未启用"
    fi
    VERIFY_IF=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1)
    VERIFY_IF=${VERIFY_IF:-eth0}
    if tc qdisc show dev "$VERIFY_IF" 2>/dev/null | grep -q "cake"; then
        echo -e "    ${GREEN}✅${NC} CAKE队列: 已启用（$VERIFY_IF）"
    elif tc qdisc show dev "$VERIFY_IF" 2>/dev/null | grep -q "fq_pie"; then
        echo -e "    ${GREEN}✅${NC} CAKE队列: 降级为FQ-PIE（$VERIFY_IF，内核不支持CAKE，FQ-PIE仍可与BBR配合）"
    elif modprobe sch_cake 2>/dev/null; then
        echo -e "    ${YELLOW}⚠️${NC} CAKE队列: 未启用（tc qdisc应用失败，已降级FQ-PIE）"
    else
        echo -e "    ${YELLOW}⚠️${NC} CAKE队列: 未启用（内核缺少sch_cake模块，已降级FQ-PIE）"
    fi
    echo ""
    if [ "$ALL_OK" = true ]; then
        echo -e "  ${GREEN}🎉 所有服务运行正常！${NC}"
    else
        echo -e "  ${YELLOW}⚠️ 部分服务异常，请检查日志${NC}"
        echo -e "  查看日志: journalctl -u singbox-sub -f"
    fi
}

print_summary() {
    SERVER_IP=$(curl -s --connect-timeout 5 https://api.ipify.org 2>/dev/null || echo "YOUR_SERVER_IP")
    CF_DOMAIN=$(grep "^CF_DOMAIN=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
    COUNTRY=$(grep "^COUNTRY_CODE=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "US")
    echo ""
    echo "=========================================="
    echo -e "${CYAN}  Singbox EPS Node 安装完成！${NC}"
    echo "=========================================="
    echo ""
    echo "📋 配置文件: $BASE_DIR/.env"
    echo ""
    if [ -n "$CF_DOMAIN" ]; then
        echo "🔗 订阅链接:"
        echo "  Base64:    https://${CF_DOMAIN}:2087/sub/${COUNTRY}"
        echo "  sing-box:  https://${CF_DOMAIN}:2087/singbox/${COUNTRY}"
    else
        echo "🔗 订阅链接:"
        echo "  Base64:    https://${SERVER_IP}:2087/sub/${COUNTRY}"
        echo "  sing-box:  https://${SERVER_IP}:2087/singbox/${COUNTRY}"
        echo ""
        echo "⚠️  建议配置CF_DOMAIN以启用CDN和SSL证书匹配"
    fi
    echo ""
    echo "📊 流量统计:"
    echo "  首页查看:  https://${CF_DOMAIN:-$SERVER_IP}:2087/"
    echo "  API接口:   https://${CF_DOMAIN:-$SERVER_IP}:2087/api/traffic"
    echo "  重置规则:  每月14号自动归零"
    echo ""
    echo "🌐 CDN优选IP（4级降级保障）:"
    echo "  主方案:    本地实测IP池（湖南电信最优）"
    echo "  备选1:     cf.001315.xyz/ct电信API"
    echo "  备选2:     WeTest.vip电信优选DNS"
    echo "  备选3:     IPDB API bestcf"
    echo ""
    echo "⚡ 系统优化（已自动完成，即时生效无需重启）:"
    echo "  BBR加速:      已启用（Google拥塞控制，不依赖丢包）"
    echo "  FQ公平队列:   已启用（为每个TCP连接独立缓冲）"
    MAIN_IF=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1) || true
    MAIN_IF=${MAIN_IF:-eth0}
    if tc qdisc show dev "$MAIN_IF" 2>/dev/null | grep -q "cake"; then
        echo "  CAKE队列:     已启用（集成FQ+PIE，抗丢包防膨胀，网卡$MAIN_IF）"
    elif tc qdisc show dev "$MAIN_IF" 2>/dev/null | grep -q "fq_pie"; then
        echo "  CAKE队列:     降级为FQ-PIE（内核不支持CAKE，FQ-PIE仍可与BBR配合，网卡$MAIN_IF）"
    else
        echo "  CAKE队列:     未启用（建议运行 bash install.sh optimize 重新优化）"
    fi
    echo "  TCP调优:       已优化（含BBR高丢包参数）"
    echo "  文件描述符:    65535"
    echo "  时区:          Asia/Shanghai"
    echo ""
    echo "📝 下一步:"
    echo "  1. 检查配置: cat /root/singbox-eps-node/.env"
    echo "  2. 如需修改: nano /root/singbox-eps-node/.env"
    echo "  3. 重启服务: systemctl restart singbox singbox-sub singbox-cdn"
    echo ""
    echo "🔧 服务管理:"
    echo "  查看状态: systemctl status singbox singbox-sub singbox-cdn"
    echo "  查看日志: journalctl -u singbox-sub -f"
    echo ""
}

cmd_reset() {
    echo ""
    echo -e "${YELLOW}⚠️  一键重装singbox应用（保留.env配置和数据）${NC}"
    echo -e "${YELLOW}    数据库(data/)和证书(cert/)不会被删除${NC}"
    echo -e "${YELLOW}    客户端无需重新配置（密码和密钥保持不变）${NC}"
    read -p "  确认重装？(y/N): " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        log_info "已取消"
        exit 0
    fi
    log_step "停止所有服务..."
    systemctl stop singbox singbox-sub singbox-cdn 2>/dev/null || true
    systemctl disable singbox singbox-sub singbox-cdn 2>/dev/null || true
    BACKUP_DIR="${BASE_DIR}.reset_backup.$(date +%Y%m%d%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    [ -f "$BASE_DIR/.env" ] && cp "$BASE_DIR/.env" "$BACKUP_DIR/"
    [ -d "$BASE_DIR/data" ] && cp -r "$BASE_DIR/data" "$BACKUP_DIR/"
    [ -d "$BASE_DIR/cert" ] && cp -r "$BASE_DIR/cert" "$BACKUP_DIR/"
    log_info "配置和数据已备份到 $BACKUP_DIR"
    rm -rf "$BASE_DIR"
    log_info "旧代码已删除"
    clone_repo
    setup_python_env
    [ -f "$BACKUP_DIR/.env" ] && cp "$BACKUP_DIR/.env" "$BASE_DIR/"
    [ -d "$BACKUP_DIR/data" ] && cp -r "$BACKUP_DIR/data" "$BASE_DIR/"
    [ -d "$BACKUP_DIR/cert" ] && cp -r "$BACKUP_DIR/cert" "$BASE_DIR/"
    log_info "配置和数据已恢复"
    generate_config
    create_systemd_services
    setup_firewall
    setup_port_hopping
    setup_swap_and_optimize
    setup_health_check_cron
    start_services
    verify_installation
    echo ""
    log_info "🎉 重装完成！配置和数据已保留"
}

cmd_reinstall() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}  ⚠️  一键重装操作系统（将清除硬盘所有数据！）${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  重装后需重新运行 ${GREEN}bash install.sh${NC} 部署singbox"
    echo ""
    check_root
    while true; do
        read -s -p "  请输入root密码: " ROOT_PASSWORD
        echo ""
        read -s -p "  请再次输入root密码: " ROOT_PASSWORD_CONFIRM
        echo ""
        if [ -z "$ROOT_PASSWORD" ]; then
            log_warn "密码不能为空，请重新输入"
            echo ""
            continue
        fi
        if [ "$ROOT_PASSWORD" != "$ROOT_PASSWORD_CONFIRM" ]; then
            log_warn "两次密码不一致，请重新输入"
            echo ""
            continue
        fi
        break
    done
    log_info "密码确认成功"
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        CURRENT_OS=$ID
        CURRENT_VERSION=$VERSION_ID
    else
        log_error "无法检测当前操作系统版本"
        exit 1
    fi
    case "$CURRENT_OS" in
        ubuntu)      REINSTALL_OS="ubuntu" ;;
        debian)      REINSTALL_OS="debian" ;;
        centos)      REINSTALL_OS="centos" ;;
        rocky)       REINSTALL_OS="rocky" ;;
        almalinux)   REINSTALL_OS="alma" ;;
        alpine)      REINSTALL_OS="alpine" ;;
        opensuse-leap) REINSTALL_OS="opensuse" ;;
        opensuse-tumbleweed) REINSTALL_OS="opensuse" ;;
        fedora)      REINSTALL_OS="fedora" ;;
        arch)        REINSTALL_OS="arch" ;;
        gentoo)      REINSTALL_OS="gentoo" ;;
        *)           REINSTALL_OS="$CURRENT_OS" ;;
    esac
    log_info "当前系统: $CURRENT_OS $CURRENT_VERSION"
    log_info "将重装为: $REINSTALL_OS $CURRENT_VERSION（保持当前版本）"
    log_info "下载系统重装脚本..."
    cd /tmp
    REINSTALL_SCRIPT=""
    curl -sS -O https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh 2>/dev/null && REINSTALL_SCRIPT="reinstall.sh" || true
    if [ -z "$REINSTALL_SCRIPT" ] || [ ! -f "reinstall.sh" ]; then
        log_info "GitHub下载失败，尝试国内镜像..."
        curl -sS -O https://cnb.cool/bin456789/reinstall/-/git/raw/main/reinstall.sh 2>/dev/null && REINSTALL_SCRIPT="reinstall.sh" || true
    fi
    if [ -z "$REINSTALL_SCRIPT" ] || [ ! -f "reinstall.sh" ]; then
        wget -q -O reinstall.sh https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh 2>/dev/null && REINSTALL_SCRIPT="reinstall.sh" || true
    fi
    if [ -z "$REINSTALL_SCRIPT" ] || [ ! -f "reinstall.sh" ]; then
        log_error "下载重装脚本失败，请检查网络连接"
        exit 1
    fi
    echo ""
    log_warn "即将开始重装操作系统，重装完成后将自动重启"
    log_warn "重启后请用新root密码SSH连接，然后运行 bash install.sh 部署singbox"
    echo ""
    log_info "开始重装 $REINSTALL_OS $CURRENT_VERSION ..."
    bash reinstall.sh "$REINSTALL_OS" "$CURRENT_VERSION" --password "$ROOT_PASSWORD"
}

cmd_optimize() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  一键优化系统（BBR+FQ+CAKE三合一加速）${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  1. BBR加速  — Google拥塞控制，不依赖丢包，主动探测带宽+RTT"
    echo -e "  2. FQ公平队列 — 为每个TCP连接独立缓冲，BBR的pacing依赖FQ"
    echo -e "  3. CAKE队列  — 集成FQ+PIE，防止缓冲区膨胀，抗丢包"
    echo -e "  即时生效，无需重启服务器"
    echo ""
    check_root
    update_system
    optimize_system
    echo ""
    echo -e "${GREEN}✅ 系统优化完成！BBR+FQ+CAKE三合一加速已启用（即时生效，无需重启）：${NC}"
    echo -e "  BBR加速:      $(sysctl net.ipv4.tcp_congestion_control 2>/dev/null | awk '{print $3}' || echo '未知')"
    echo -e "  默认队列:     $(sysctl net.core.default_qdisc 2>/dev/null | awk '{print $3}' || echo '未知')"
    MAIN_IF=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1)
    MAIN_IF=${MAIN_IF:-eth0}
    if tc qdisc show dev "$MAIN_IF" 2>/dev/null | grep -q "cake"; then
        echo -e "  CAKE队列:     已启用（$MAIN_IF，集成FQ+PIE，抗丢包防膨胀）"
    elif tc qdisc show dev "$MAIN_IF" 2>/dev/null | grep -q "fq_pie"; then
        echo -e "  CAKE队列:     降级为FQ-PIE（$MAIN_IF，内核不支持CAKE，FQ-PIE仍可与BBR配合）"
    else
        echo -e "  CAKE队列:     未启用（$MAIN_IF，建议检查内核模块）"
    fi
    echo -e "  文件描述符:    65535"
    echo -e "  时区:          Asia/Shanghai"
    echo ""
}

cmd_help() {
    echo ""
    echo -e "${CYAN}Singbox EPS Node 一键脚本 v2.0.0${NC}"
    echo ""
    echo "用法:"
    echo "  bash install.sh              全新安装（自动优化系统+交互式配置）"
    echo "  bash install.sh reinstall    一键重装操作系统（需输入root密码，装完自动重启）"
    echo "  bash install.sh reset        一键重装singbox（保留配置和数据，客户端无需重配）"
    echo "  bash install.sh optimize     一键优化系统（BBR+FQ+CAKE三合一，即时生效无需重启）"
    echo "  bash install.sh help         显示此帮助"
    echo ""
    echo "子命令说明:"
    echo "  reinstall  重装操作系统（bin456789/reinstall）"
    echo "             - 自动检测当前OS版本，重装为相同版本"
    echo "             - 需输入root密码（两次确认），作为新系统登录密码"
    echo "             - 重装后需重新运行 bash install.sh 部署singbox"
    echo "  reset      重装singbox应用（保留.env配置和数据库）"
    echo "             - 保留所有密码和密钥，客户端无需重新配置"
    echo "             - 保留流量统计数据和证书"
    echo ""
    echo "安装流程（全自动，无需手动操作）："
    echo "  阶段1: 系统更新 → 安装依赖 → BBR+FQ+CAKE三合一加速 → 系统优化"
    echo "  阶段2: 卸载旧面板 → 安装singbox → 交互式配置 → 启动服务"
    echo ""
    echo "BBR+FQ+CAKE三合一加速（海外代理最优方案）："
    echo "  1. BBR加速   — Google拥塞控制，不依赖丢包，主动探测带宽+RTT"
    echo "  2. FQ公平队列 — 为每个TCP连接独立缓冲，BBR的pacing依赖FQ"
    echo "  3. CAKE队列  — 集成FQ+PIE，防止缓冲区膨胀，抗丢包"
    echo "  ⚠️ 即时生效，无需重启服务器"
    echo "  ⚠️ 内核不支持CAKE时自动降级为FQ-PIE（比FQ更适应高丢包环境）"
    echo ""
}

main() {
    case "${1:-}" in
        reset)
            cmd_reset
            ;;
        reinstall)
            cmd_reinstall
            ;;
        optimize)
            cmd_optimize
            ;;
        help|--help|-h)
            cmd_help
            ;;
        "")
            echo ""
            echo "=========================================="
            echo -e "${CYAN}  Singbox EPS Node 一键安装脚本 v2.0.0${NC}"
            echo "=========================================="
            echo ""
            check_root
            detect_os
            update_system
            install_dependencies
            optimize_system
            uninstall_old_panels
            install_singbox
            clone_repo
            setup_python_env
            generate_uuids_and_passwords
            generate_reality_keys
            create_env_file
            generate_config
            setup_certificate
            setup_firewall
            setup_port_hopping
            create_systemd_services
            setup_swap_and_optimize
            setup_health_check_cron
            start_services
            verify_installation
            print_summary
            ;;
        *)
            log_error "未知命令: $1"
            cmd_help
            exit 1
            ;;
    esac
}

main "$@"
