# Singbox Manager 架构设计

## 项目概述

Singbox Manager 是一个基于 Singbox 内核的代理解决方案，不依赖任何面板界面，纯脚本化管理。

**设计目标**：
- 极简架构，模块化设计
- 单一订阅链接，包含所有节点
- 支持 CDN 优选 IP 自动分配
- Hysteria2 端口跳跃，重启后规则持久化
- Cloudflare API 支持长期证书
- 域名/IP 自动判断

## 目录结构

```
singbox-manager/
├── install.sh              # 一键安装脚本 v1.0.7
├── README.md               # 项目说明
├── docs/
│   ├── architecture.md     # 架构设计文档
│   └── usage.md            # 使用说明
└── scripts/
    ├── __init__.py          # 包初始化
    ├── config.py            # 统一配置管理
    ├── logger.py            # 日志管理
    ├── config_generator.py  # Singbox 配置生成
    ├── subscription_service.py # 订阅服务
    ├── cdn_monitor.py       # CDN 监控
    └── cert_manager.py      # 证书管理
```

## 节点命名规则

**格式**: `ePS-{国家}-{协议名称}`

| 节点名称 | 协议 | IP类型 | 说明 |
|---------|------|--------|------|
| ePS-JP-VLESS-Reality | VLESS + Reality | 直连IP | 殖民节点，苹果域名伪装 |
| ePS-JP-VLESS-WS | VLESS + WebSocket | CDN IP | CDN 节点 |
| ePS-JP-Trojan-WS | Trojan + WebSocket | CDN IP | CDN 节点 |
| ePS-JP-Hysteria2 | Hysteria2 | 直连IP | 直连节点，端口跳跃 21000-21200 |
| ePS-JP-SOCKS5 | SOCKS5 | 本地 | 本地代理（不在订阅中） |

## 一键安装脚本菜单

```bash
==============================================
    Singbox Manager 一键安装脚本 v1.0.7
==============================================

  1. 完整安装（推荐）
  2. 仅安装 Singbox 内核
  3. 配置 CDN 加速
  4. 生成订阅链接
  5. 一键重装系统密码
  6. 退出
```

### 选项说明

| 选项 | 功能 |
|------|------|
| 1 | 完整安装（更新系统 → 卸载旧面板 → 安装Singbox → 配置证书 → 设置端口跳跃 → 生成配置 → 启动服务 → 配置CDN → 生成订阅） |
| 2 | 仅安装 Singbox 内核 |
| 3 | 配置 CDN 加速 |
| 4 | 生成订阅链接 |
| 5 | 一键重装系统密码（确认当前 root 密码） |
| 6 | 退出脚本 |

## 核心模块

### 1. config.py - 配置中心

**职责**：集中管理所有配置参数

**核心功能**：
- 服务器 IP、域名配置
- 端口配置（订阅、Singbox、各协议）
- Reality 配置参数
- CDN 配置参数
- Hysteria2 端口范围（21000-21200）
- 节点命名规则

### 2. logger.py - 日志管理

**职责**：统一的日志记录

**核心功能**：
- 文件日志 + 控制台日志
- 统一日志格式
- 可配置日志级别

### 3. config_generator.py - 配置生成

**职责**：生成 Singbox 配置文件

**核心功能**：
- 生成 5 个入站配置（VLESS Reality、VLESS WS、Trojan WS、Hysteria2、SOCKS5）
- 自动生成密码和 UUID
- 保存配置到 config.json

### 4. subscription_service.py - 订阅服务

**职责**：提供 HTTPS 订阅服务

**核心功能**：
- Flask 应用，监听 2096 端口
- Base64 编码的订阅内容
- 包含 4 个节点（Reality、VLESS WS、Trojan WS、Hysteria2）
- 随机选择 Hysteria2 跳跃端口（21000-21200）
- **智能域名/IP判断**：有域名用域名，无域名用IP
- **CDN IP优先**：WebSocket 节点优先使用 CDN IP

### 5. cdn_monitor.py - CDN 监控

**职责**：自动获取并分配 CDN 优选 IP

**核心功能**：
- 从 CDN 数据库获取优选 IP
- 随机选择 1 个 IP 分配给所有 CDN 协议
- 支持守护进程模式
- 自动更新 singbox.db

### 6. cert_manager.py - 证书管理

**职责**：SSL 证书管理

**核心功能**：
- **优先**：使用 Cloudflare API 申请源证书（15年有效期）
- **备用**：自签证书（365天）
- 自动续签检查
- iptables 持久化配置

## 安装流程

```
1. 更新系统 (apt-get update && apt-get upgrade)
2. 安装依赖 (curl wget unzip python3 pip cron iptables-persistent)
3. 卸载旧面板 (s-ui x-ui maro)
4. 下载安装 Singbox 内核
5. 创建目录结构
6. 部署 Python 脚本
7. 生成证书
8. 设置 Hysteria2 端口跳跃规则 (21000-21200)
9. 生成 Singbox 配置
10. 创建 Systemd 服务
11. 启动服务
12. 配置 CDN 加速
13. 生成订阅链接
```

## 证书逻辑

### 优先级

1. **Cloudflare API 证书**（优先）
   - 使用 `CF_API_TOKEN` 通过 Cloudflare API 申请源证书
   - 有效期：15年（5475天）
   - 适合长期使用

2. **自签名证书**（备用）
   - 如果 CF API 失败或未配置 Token
   - 有效期：365天
   - 每年需要手动更新

### .env 配置

```bash
SERVER_IP=54.250.149.157        # 服务器IP（必填）
CF_DOMAIN=                      # 域名（可选，不填则用IP）
CF_API_TOKEN=                   # Cloudflare API Token（可选）
VLESS_UUID=                     # VLESS UUID
VLESS_WS_UUID=                 # VLESS WS UUID
TROJAN_PASSWORD=               # Trojan 密码
HYSTERIA2_PASSWORD=            # Hysteria2 密码
REALITY_PRIVATE_KEY=           # Reality 私钥
REALITY_PUBLIC_KEY=            # Reality 公钥
```

## 订阅地址选择逻辑

| 配置情况 | 订阅服务地址 | CDN节点地址 |
|---------|------------|-----------|
| 只有IP | IP | CDN IP 或 IP |
| 只有域名 | 域名 | CDN IP 或 域名 |
| 有IP和域名 | 域名 | CDN IP 或 域名 |

## 技术参数

| 参数 | 值 |
|------|-----|
| 服务器IP | 54.250.149.157 |
| 域名 | jp1.290372913.xyz（可选） |
| 订阅端口 | 2096 |
| Singbox 端口 | 443 |
| VLESS WS 端口 | 10001 |
| Trojan WS 端口 | 10002 |
| Hysteria2 端口 | 4433 |
| Hysteria2 跳跃范围 | 21000-21200 |
| SOCKS5 端口 | 1080 |
| Reality SNI | www.apple.com |
| Reality 目标 | www.apple.com:443 |
| CDN 优选 | 前5个随机选1个 |

## Systemd 服务

| 服务名 | 说明 |
|--------|------|
| singbox | Singbox 主服务 |
| singbox-sub | 订阅服务（Flask） |
| singbox-cdn | CDN 监控服务 |

## iptables 持久化

Hysteria2 端口跳跃规则使用 iptables-persistent 持久化：

```bash
# 端口范围：21000-21200
iptables -t nat -A PREROUTING -p udp --dport 21000:21200 -j DNAT --to-destination :4433
iptables -t nat -A PREROUTING -p tcp --dport 21000:21200 -j DNAT --to-destination :4433

# 保存规则
netfilter-persistent save
```

重启后规则自动恢复。
