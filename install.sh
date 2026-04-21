#!/bin/bash
# ============================================================
# Singbox EPS Node 一键安装脚本
# 版本: v1.0.74
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

# ============ 默认配置（写死，新VPS也能自动填入）============
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
        net-tools procps iproute2

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

# 设置default_qdisc为cake（CAKE集成FQ+PIE）
set_default_qdisc_cake() {
    if grep -q "^net.core.default_qdisc=" /etc/sysctl.conf 2>/dev/null; then
        sed -i 's|^net.core.default_qdisc=.*|net.core.default_qdisc=cake|' /etc/sysctl.conf
    else
        echo "net.core.default_qdisc=cake" >> /etc/sysctl.conf
    fi
}

# 降级设置default_qdisc为fq_pie（比fq更适应高丢包环境）
set_default_qdisc_fq_pie() {
    if grep -q "^net.core.default_qdisc=" /etc/sysctl.conf 2>/dev/null; then
        sed -i 's|^net.core.default_qdisc=.*|net.core.default_qdisc=fq_pie|' /etc/sysctl.conf
    else
