#!/bin/bash
# ============================================================
# Singbox EPS Node 一键安装脚本
# 版本: v1.0.64
# 用途: 新VPS全自动部署（含系统优化+CDN优选+流量统计）
# 使用: bash <(curl -sL https://raw.githubusercontent.com/Alan-zzh/singbox-eps-node/main/install.sh)
#
# 【自动化功能清单】
# 阶段1-系统准备（全自动，无需用户操作）：
#   1. 系统更新：apt upgrade + 语言包 + 时区
#   2. 安装依赖：curl/wget/python3/openssl/sqlite3等
#   3. 3大网络加速：BBR加速+TCP FastOpen+TCP调优（即时生效，无需重启）
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

# ============================================================
# 阶段1-步骤1：系统更新（全自动）
# 包含：apt升级系统、安装语言包、设置时区
# ============================================================
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

    # 设置UTF-8编码
    locale-gen en_US.UTF-8 2>/dev/null || true
    update-locale LANG=en_US.UTF-8 2>/dev/null || true

    # 设置时区
    timedatectl set-timezone Asia/Shanghai 2>/dev/null || true

    log_info "系统更新完成（apt upgrade + 语言包 + 时区）"
}

# ============================================================
# 阶段1-步骤2：安装依赖（全自动）
# ============================================================
install_dependencies() {
    log_step "【阶段1-步骤2/4】安装运行依赖..."

    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        curl wget unzip python3 python3-pip python3-venv \
        cron iptables-persistent sqlite3 dnsutils openssl \
        net-tools procps

    log_info "运行依赖安装完成"
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
# 阶段1-步骤3+4：3大网络加速 + 系统优化（全自动，即时生效，无需重启）
#
# 3大网络加速：
#   1. BBR加速 — Google拥塞控制算法，替代默认Cubic，带宽利用率翻倍
#   2. TCP FastOpen — 减少TCP握手延迟，首次连接即可携带数据（=3=客户端+服务端均启用）
#   3. TCP调优 — 缓冲区/连接队列/保活参数优化，提升高并发性能
#
# 系统优化：
#   4. 文件描述符提升到65535
#
# ⚠️ sysctl -p 即时生效，不需要重启服务器
# ============================================================
optimize_system() {
    log_step "【阶段1-步骤3/4】启用3大网络加速（BBR+TCP FastOpen+TCP调优）..."

    # 1. BBR加速（防止重复追加）
    if ! sysctl net.ipv4.tcp_congestion_control 2>/dev/null | grep -q "bbr"; then
        log_info "加速1/3：启用BBR加速（替代Cubic，带宽利用率翻倍）..."
        grep -q "^net.core.default_qdisc=fq" /etc/sysctl.conf 2>/dev/null || echo "net.core.default_qdisc=fq" >> /etc/sysctl.conf
        grep -q "^net.ipv4.tcp_congestion_control=bbr" /etc/sysctl.conf 2>/dev/null || echo "net.ipv4.tcp_congestion_control=bbr" >> /etc/sysctl.conf
    else
        log_info "加速1/3：BBR已启用，跳过"
    fi

    # 2. TCP FastOpen + TCP调优（逐项检查，防止重复追加）
    log_info "加速2/3：启用TCP FastOpen（减少握手延迟）..."
    log_info "加速3/3：TCP调优（缓冲区+连接队列+保活参数）..."
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
    log_info "3大网络加速已启用（即时生效，无需重启）"

    # 3. 文件描述符限制（防止重复追加）
    if ! grep -q "65535" /etc/security/limits.conf 2>/dev/null; then
        log_info "【阶段1-步骤4/4】提升文件描述符限制到65535..."
        cat >> /etc/security/limits.conf << 'EOF'
* soft nofile 65535
* hard nofile 65535
root soft nofile 65535
root hard nofile 65535
EOF
    fi

    log_info "阶段1完成：系统更新+依赖+3大加速+优化（全部即时生效，无需重启）"
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

    # 交互式询问：是否配置AI住宅代理
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

    # 交互式询问：Cloudflare域名
    CF_DOMAIN_INPUT=""
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  Cloudflare域名配置（可选）${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  配置后可启用CDN加速和正式SSL证书"
    echo -e "  如果没有域名，直接回车跳过（使用自签名证书）"
    echo ""
    read -p "  Cloudflare域名（留空跳过）: " CF_DOMAIN_INPUT

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
CF_API_TOKEN=
COUNTRY_CODE=JP
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
    echo "⚡ 系统优化（已自动完成，即时生效无需重启）:"
    echo "  BBR加速:      已启用"
    echo "  TCP FastOpen:  已启用"
    echo "  TCP调优:       已优化"
    echo "  文件描述符:    65535"
    echo "  时区:          Asia/Shanghai"
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

# ============================================================
# 子命令：一键重装（保留.env，重新部署所有代码和服务）
# ============================================================
cmd_reset() {
    echo ""
    echo -e "${YELLOW}⚠️  一键重装将保留.env配置，重新部署所有代码和服务${NC}"
    echo -e "${YELLOW}    数据库(data/)和证书(cert/)不会被删除${NC}"
    read -p "  确认重装？(y/N): " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        log_info "已取消"
        exit 0
    fi

    log_step "停止所有服务..."
    systemctl stop singbox singbox-sub singbox-cdn 2>/dev/null || true
    systemctl disable singbox singbox-sub singbox-cdn 2>/dev/null || true

    # 备份.env和数据
    BACKUP_DIR="${BASE_DIR}.reset_backup.$(date +%Y%m%d%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    [ -f "$BASE_DIR/.env" ] && cp "$BASE_DIR/.env" "$BACKUP_DIR/"
    [ -d "$BASE_DIR/data" ] && cp -r "$BASE_DIR/data" "$BACKUP_DIR/"
    [ -d "$BASE_DIR/cert" ] && cp -r "$BASE_DIR/cert" "$BACKUP_DIR/"
    log_info "配置和数据已备份到 $BACKUP_DIR"

    # 删除旧代码
    rm -rf "$BASE_DIR"
    log_info "旧代码已删除"

    # 重新部署
    clone_repo
    setup_python_env

    # 恢复.env和数据
    [ -f "$BACKUP_DIR/.env" ] && cp "$BACKUP_DIR/.env" "$BASE_DIR/"
    [ -d "$BACKUP_DIR/data" ] && cp -r "$BACKUP_DIR/data" "$BASE_DIR/"
    [ -d "$BACKUP_DIR/cert" ] && cp -r "$BACKUP_DIR/cert" "$BASE_DIR/"
    log_info "配置和数据已恢复"

    # 重新生成配置和服务
    generate_config
    create_systemd_services
    setup_firewall
    setup_port_hopping
    setup_health_check_cron
    start_services
    verify_installation

    echo ""
    log_info "🎉 重装完成！配置和数据已保留"
}

# ============================================================
# 子命令：一键优化系统（BBR+TCP FastOpen+TCP调优+文件描述符）
# 3大网络加速：
#   1. BBR加速 — Google拥塞控制算法，替代默认Cubic，大幅提升带宽利用率
#   2. TCP FastOpen — 减少TCP握手延迟，首次连接即可携带数据
#   3. TCP调优 — 缓冲区/连接队列/保活参数优化，提升高并发性能
# ============================================================
cmd_optimize() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  一键优化系统（3大网络加速）${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  1. BBR加速     — Google拥塞控制，替代Cubic，带宽利用率翻倍"
    echo -e "  2. TCP FastOpen — 减少握手延迟，首次连接即可携带数据"
    echo -e "  3. TCP调优      — 缓冲区/连接队列/保活参数，提升高并发"
    echo -e "  即时生效，无需重启服务器"
    echo ""

    check_root
    update_system
    optimize_system

    echo ""
    echo -e "${GREEN}✅ 系统优化完成！3大网络加速已启用（即时生效，无需重启）：${NC}"
    echo -e "  BBR加速:      $(sysctl net.ipv4.tcp_congestion_control 2>/dev/null | awk '{print $3}' || echo '未知')"
    echo -e "  TCP FastOpen:  $(sysctl net.ipv4.tcp_fastopen 2>/dev/null | awk '{print $3}' || echo '未知')"
    echo -e "  文件描述符:    65535"
    echo -e "  时区:          Asia/Shanghai"
    echo ""
}

# ============================================================
# 子命令：显示帮助
# ============================================================
cmd_help() {
    echo ""
    echo -e "${CYAN}Singbox EPS Node 一键脚本 v1.0.64${NC}"
    echo ""
    echo "用法:"
    echo "  bash install.sh              全新安装（自动优化系统+交互式配置）"
    echo "  bash install.sh reset        一键重装（保留配置和数据）"
    echo "  bash install.sh optimize     一键优化系统（更新+3大加速，即时生效无需重启）"
    echo "  bash install.sh help         显示此帮助"
    echo ""
    echo "安装流程（全自动，无需手动操作）："
    echo "  阶段1: 系统更新 → 安装依赖 → 3大网络加速 → 系统优化"
    echo "  阶段2: 卸载旧面板 → 安装singbox → 交互式配置 → 启动服务"
    echo ""
    echo "3大网络加速（安装时自动启用，也可单独运行optimize）："
    echo "  1. BBR加速      — Google拥塞控制算法，替代默认Cubic"
    echo "  2. TCP FastOpen  — 减少TCP握手延迟（=3表示客户端+服务端均启用）"
    echo "  3. TCP调优       — 缓冲区/连接队列/保活参数优化"
    echo "  ⚠️ 即时生效，无需重启服务器"
    echo ""
}

main() {
    # 解析子命令
    case "${1:-}" in
        reset)
            cmd_reset
            ;;
        optimize)
            cmd_optimize
            ;;
        help|--help|-h)
            cmd_help
            ;;
        "")
            # 无参数：全新安装
            echo ""
            echo "=========================================="
            echo -e "${CYAN}  Singbox EPS Node 一键安装脚本 v1.0.64${NC}"
            echo "=========================================="
            echo ""

            # ===== 阶段1：系统准备（全自动，无需用户操作）=====
            check_root
            detect_os
            update_system
            install_dependencies
            optimize_system

            # ===== 阶段2：部署服务（交互式配置）=====
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
