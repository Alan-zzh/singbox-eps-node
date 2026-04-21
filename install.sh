#!/bin/bash
# ============================================================
# Singbox EPS Node 一键安装脚本
# 版本: v1.0.62
# 用途: 新VPS全自动部署（含系统优化+CDN优选+流量统计）
# 使用: bash <(curl -sL https://raw.githubusercontent.com/Alan-zzh/singbox-eps-node/main/install.sh)
#
# 【自动化功能清单】
# 1. 系统优化：BBR加速+TCP调优+文件描述符+内核参数
# 2. CDN优选IP：4级降级保障（本地池→001315→WeTest→IPDB）
# 3. 流量统计：按月统计+每月14号自动归零+首页显示
# 4. 健康检查：每5分钟自动检测+异常自动重启
# 5. 证书续签：每月1号自动检查+到期自动续签
# 6. HY2端口跳跃：UDP+TCP双协议保障+iptables持久化
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

BASE_DIR="/root/singbox-eps-node"
REPO_URL="https://github.com/Alan-zzh/singbox-eps-node"

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

install_dependencies() {
    log_step "安装系统依赖..."
    apt-get update -y
    apt-get install -y curl wget unzip python3 python3-pip python3-venv cron iptables-persistent sqlite3 dnsutils openssl
}

uninstall_old_panels() {
    log_step "检查并卸载旧面板..."
    for panel in s-ui x-ui marzban 3x-ui; do
        if systemctl is-active --quiet "$panel" 2>/dev/null; then
            log_warn "检测到 $panel 正在运行，正在卸载..."
            systemctl stop "$panel" 2>/dev/null || true
            systemctl disable "$panel" 2>/dev/null || true
        fi
    done
}

# ============================================================
# 系统优化（全自动，无需用户手动操作）
# 包含：BBR加速、TCP调优、文件描述符、内核参数
# ============================================================
optimize_system() {
    log_step "优化系统参数（BBR+TCP+文件描述符）..."

    # 1. 启用BBR加速（防止重复追加）
    if ! sysctl net.ipv4.tcp_congestion_control 2>/dev/null | grep -q "bbr"; then
        log_info "启用BBR加速..."
        grep -q "^net.core.default_qdisc=fq" /etc/sysctl.conf 2>/dev/null || echo "net.core.default_qdisc=fq" >> /etc/sysctl.conf
        grep -q "^net.ipv4.tcp_congestion_control=bbr" /etc/sysctl.conf 2>/dev/null || echo "net.ipv4.tcp_congestion_control=bbr" >> /etc/sysctl.conf
    else
        log_info "BBR已启用，跳过"
    fi

    # 2. TCP调优（逐项检查，防止重复追加）
    log_info "优化TCP参数..."
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
net.ipv4.tcp_keepalive_probes=10"
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
    log_info "内核参数已优化"

    # 3. 文件描述符限制（防止重复追加）
    if ! grep -q "65535" /etc/security/limits.conf 2>/dev/null; then
        log_info "提升文件描述符限制..."
        cat >> /etc/security/limits.conf << 'EOF'
* soft nofile 65535
* hard nofile 65535
root soft nofile 65535
root hard nofile 65535
EOF
    fi

    # 4. 时区设置
    timedatectl set-timezone Asia/Shanghai 2>/dev/null || true
    log_info "时区已设置为Asia/Shanghai"

    log_info "系统优化完成（BBR+TCP+文件描述符+时区）"
}

install_singbox() {
    log_step "安装 Singbox 内核..."
    if command -v singbox &>/dev/null; then
        log_info "Singbox 已安装: $(singbox version 2>/dev/null | head -1 || echo '未知版本')"
        return
    fi

    ARCH=$(uname -m)
    case $ARCH in
        x86_64)  SINGBOX_ARCH="amd64" ;;
        aarch64) SINGBOX_ARCH="arm64" ;;
        *)       log_error "不支持的架构: $ARCH"; exit 1 ;;
    esac

    SINGBOX_VER="1.11.3"
    SINGBOX_URL="https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VER}/sing-box-${SINGBOX_VER}-linux-${SINGBOX_ARCH}.tar.gz"

    log_info "下载 Singbox v${SINGBOX_VER} (${SINGBOX_ARCH})..."
    cd /tmp
    wget -q "$SINGBOX_URL" -O singbox.tar.gz
    tar -xzf singbox.tar.gz
    cp "sing-box-${SINGBOX_VER}-linux-${SINGBOX_ARCH}/sing-box" /usr/local/bin/singbox
    chmod +x /usr/local/bin/singbox
    rm -rf singbox.tar.gz "sing-box-${SINGBOX_VER}-linux-${SINGBOX_ARCH}"
    log_info "Singbox 安装完成: $(singbox version | head -1)"
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
    python3 -m venv venv
    source venv/bin/activate
    if [ -f "requirements.txt" ]; then
        pip install --quiet -r requirements.txt
    else
        pip install --quiet flask python-dotenv
    fi
    deactivate
}

generate_uuids_and_passwords() {
    log_step "生成协议密码和UUID..."

    VLESS_UUID=$(python3 -c "import uuid; print(uuid.uuid4())")
    VLESS_WS_UUID=$(python3 -c "import uuid; print(uuid.uuid4())")
    TROJAN_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(16))")
    HYSTERIA2_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(16))")

    log_info "UUID和密码已生成"
}

generate_reality_keys() {
    log_step "生成Reality密钥对..."
    REALITY_OUTPUT=$(singbox generate reality-keypair 2>/dev/null)
    REALITY_PRIVATE_KEY=$(echo "$REALITY_OUTPUT" | grep "PrivateKey" | awk '{print $2}')
    REALITY_PUBLIC_KEY=$(echo "$REALITY_OUTPUT" | grep "PublicKey" | awk '{print $2}')

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

    cat > "$BASE_DIR/.env" << EOF
# Singbox EPS Node 环境变量配置
# 由安装脚本自动生成于 $(date '+%Y-%m-%d %H:%M:%S')

# ============ 必填 ============
SERVER_IP=${SERVER_IP}
CF_DOMAIN=

# ============ 协议密码 ============
VLESS_UUID=${VLESS_UUID}
VLESS_WS_UUID=${VLESS_WS_UUID}
TROJAN_PASSWORD=${TROJAN_PASSWORD}
HYSTERIA2_PASSWORD=${HYSTERIA2_PASSWORD}
REALITY_PRIVATE_KEY=${REALITY_PRIVATE_KEY}
REALITY_PUBLIC_KEY=${REALITY_PUBLIC_KEY}

# ============ 可选 ============
CF_API_TOKEN=
COUNTRY_CODE=JP
SUB_TOKEN=
AI_SOCKS5_SERVER=
AI_SOCKS5_PORT=
AI_SOCKS5_USER=
AI_SOCKS5_PASS=
TG_BOT_TOKEN=
TG_ADMIN_CHAT_ID=
EOF

    chmod 600 "$BASE_DIR/.env"
    log_info ".env 已创建 (服务器IP: ${SERVER_IP:-未检测到，请手动填写})"
}

generate_config() {
    log_step "生成Singbox配置..."
    cd "$BASE_DIR"
    source venv/bin/activate
    python3 scripts/config_generator.py
    deactivate
}

setup_certificate() {
    log_step "配置SSL证书..."
    cd "$BASE_DIR"
    source venv/bin/activate

    CF_API=$(python3 -c "
import os
from dotenv import load_dotenv
load_dotenv('.env')
token = os.getenv('CF_API_TOKEN', '')
domain = os.getenv('CF_DOMAIN', '')
print(f'{token}|{domain}')
")

    CF_TOKEN=$(echo "$CF_API" | cut -d'|' -f1)
    CF_DOM=$(echo "$CF_API" | cut -d'|' -f2)

    if [ -n "$CF_TOKEN" ] && [ -n "$CF_DOM" ]; then
        log_info "检测到CF_API_TOKEN和CF_DOMAIN，尝试申请Cloudflare证书..."
        python3 scripts/cert_manager.py --cf-cert || python3 scripts/cert_manager.py
    else
        log_info "未配置CF_API_TOKEN，使用自签名证书..."
        python3 scripts/cert_manager.py
    fi
    deactivate
}

setup_port_hopping() {
    log_step "设置Hysteria2端口跳跃规则 (21000-21200 → 443, UDP+TCP)..."
    cd "$BASE_DIR"
    source venv/bin/activate
    python3 scripts/cert_manager.py --setup-iptables
    deactivate
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
ExecStart=${BASE_DIR}/venv/bin/python3 scripts/subscription_service.py
Restart=on-failure
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/singbox-cdn.service << EOF
[Unit]
Description=Singbox CDN Monitor Service (4级降级保障)
After=network.target singbox.service

[Service]
Type=simple
WorkingDirectory=${BASE_DIR}
ExecStart=${BASE_DIR}/venv/bin/python3 scripts/cdn_monitor.py
Restart=on-failure
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log_info "Systemd服务已创建"
}

# ============================================================
# 防火墙配置（必须在端口跳跃之前！铁律12）
# iptables -F会清空所有规则，如果先设置端口跳跃再重置防火墙，
# 端口跳跃规则会被清除。安装脚本执行顺序：防火墙 → 端口跳跃 → 服务启动
# ============================================================
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
    # 健康检查每5分钟
    (crontab -l 2>/dev/null | grep -v "health_check.sh"; echo "*/5 * * * * ${BASE_DIR}/scripts/health_check.sh >> ${BASE_DIR}/logs/health_check.log 2>&1") | crontab -
    # 证书续签每月1号凌晨3点
    (crontab -l 2>/dev/null | grep -v "cert_manager.py"; echo "0 3 1 * * cd ${BASE_DIR} && venv/bin/python3 scripts/cert_manager.py --renew >> ${BASE_DIR}/logs/cert_renew.log 2>&1") | crontab -
    log_info "定时任务已配置（健康检查每5分钟 + 证书续签每月1号凌晨3点）"
}

start_services() {
    log_step "启动所有服务..."
    systemctl enable singbox singbox-sub singbox-cdn
    systemctl start singbox
    sleep 2
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

    echo ""
    echo "=========================================="
    echo -e "${CYAN}  Singbox EPS Node 安装完成！${NC}"
    echo "=========================================="
    echo ""
    echo "📋 配置文件: $BASE_DIR/.env"
    echo ""

    if [ -n "$CF_DOMAIN" ]; then
        echo "🔗 订阅链接:"
        echo "  Base64:    https://${CF_DOMAIN}:2087/sub/JP"
        echo "  sing-box:  https://${CF_DOMAIN}:2087/singbox/JP"
    else
        echo "🔗 订阅链接（请先在.env中配置CF_DOMAIN）:"
        echo "  Base64:    https://${SERVER_IP}:2087/sub/JP"
        echo "  sing-box:  https://${SERVER_IP}:2087/singbox/JP"
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
    echo "⚡ 系统优化（已自动完成）:"
    echo "  BBR加速:   已启用"
    echo "  TCP调优:   已优化"
    echo "  文件描述符: 65535"
    echo "  时区:      Asia/Shanghai"
    echo ""
    echo "📝 下一步:"
    echo "  1. 编辑配置: nano $BASE_DIR/.env"
    echo "  2. 如有域名，填写CF_DOMAIN和CF_API_TOKEN"
    echo "  3. 重启服务: systemctl restart singbox singbox-sub singbox-cdn"
    echo ""
    echo "🔧 服务管理:"
    echo "  查看状态: systemctl status singbox singbox-sub singbox-cdn"
    echo "  查看日志: journalctl -u singbox-sub -f"
    echo ""
}

main() {
    echo ""
    echo "=========================================="
    echo -e "${CYAN}  Singbox EPS Node 一键安装脚本 v1.0.62${NC}"
    echo "=========================================="
    echo ""

    check_root
    detect_os
    install_dependencies
    uninstall_old_panels
    optimize_system
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
    setup_health_check_cron
    start_services
    verify_installation
    print_summary
}

main "$@"
