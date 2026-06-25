#!/bin/bash
# WARP DNS解锁脚本 - 薄封装，调用主install.sh
# 用法:
#   sudo bash scripts/warp_unlock.sh          # 安装WARP解锁
#   sudo bash scripts/warp_unlock.sh off      # 关闭WARP解锁

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_SH="$SCRIPT_DIR/../install.sh"

if [ ! -f "$INSTALL_SH" ]; then
    echo "[错误] 找不到install.sh，请确保在项目目录中运行"
    exit 1
fi

ACTION="${1:-install}"
exec bash "$INSTALL_SH" warp-unlock "$ACTION"
