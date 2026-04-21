# Singbox EPS Node 使用说明

**版本**: v1.0.75 | **更新**: 2026-04-22

## 快速开始

### 一键安装

```bash
bash <(curl -sL https://raw.githubusercontent.com/Alan-zzh/singbox-eps-node/main/install.sh)
```

### 安装流程（全自动）

**阶段1-系统准备（全自动，无需操作）**：
1. 系统更新：apt upgrade + 语言包 + 时区
2. 安装依赖：curl/wget/python3/openssl/sqlite3等
3. BBR+FQ+CAKE三合一加速（即时生效，无需重启）
4. 系统优化：文件描述符+内核参数

**阶段2-部署服务（全自动配置）**：
5. 卸载旧面板 → 安装singbox → 部署项目
6. 自动检测国家代码 + 自动填入CF_DOMAIN和CF_API_TOKEN
7. 生成配置+证书+防火墙+端口跳跃
8. 启动服务+验证

### 子命令

| 命令 | 功能 |
|------|------|
| `bash install.sh` | 全新安装 |
| `bash install.sh reinstall` | 重装操作系统（需root密码，装完自动重启） |
| `bash install.sh reset` | 重装singbox应用（保留配置和数据，客户端无需重配） |
| `bash install.sh optimize` | 一键优化系统（BBR+FQ+CAKE三合一，即时生效） |
| `bash install.sh help` | 显示帮助 |

### 获取订阅链接

订阅地址格式：`https://{域名}:2087/sub/{国家代码}`

国家代码根据服务器IP自动检测（US/JP/SG/HK等）

## 节点列表

| 节点名称 | 协议 | 用途 | 端口 |
|---------|------|------|------|
| ePS-{CC}-VLESS-Reality | VLESS + Reality | 直连节点 | 443 |
| ePS-{CC}-VLESS-WS-CDN | VLESS + WebSocket | CDN节点 | 8443 |
| ePS-{CC}-VLESS-HTTPUpgrade-CDN | VLESS + HTTPUpgrade | CDN节点 | 2053 |
| ePS-{CC}-Trojan-WS-CDN | Trojan + WebSocket | CDN节点 | 2083 |
| ePS-{CC}-Hysteria2 | Hysteria2 + 端口跳跃 | 直连节点 | 443 (跳跃: 21000-21200) |

> {CC} = 国家代码，自动检测（如US、JP、SG）

## 服务管理

### 查看服务状态

```bash
systemctl status singbox        # Singbox内核
systemctl status singbox-sub    # 订阅服务
systemctl status singbox-cdn    # CDN监控
```

### 重启服务

```bash
systemctl restart singbox singbox-sub singbox-cdn
```

### 查看日志

```bash
journalctl -u singbox -f         # Singbox日志
journalctl -u singbox-sub -f     # 订阅服务日志
journalctl -u singbox-cdn -f     # CDN监控日志
```

## 配置文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| 环境变量 | `/root/singbox-eps-node/.env` | 所有密码和密钥 |
| Singbox配置 | `/root/singbox-eps-node/config.json` | Singbox主配置 |
| 证书 | `/root/singbox-eps-node/cert/` | SSL证书目录 |
| 数据库 | `/root/singbox-eps-node/data/singbox.db` | CDN IP存储+流量统计 |
| 健康检查日志 | `/root/singbox-eps-node/logs/` | 健康检查日志 |

## BBR+FQ+CAKE三合一加速

海外代理服务器最优方案，安装时自动启用：

| 加速 | 作用 |
|------|------|
| BBR | 智能调节发送速率，不依赖丢包信号 |
| FQ | 公平分配带宽，BBR的pacing依赖FQ |
| CAKE | 主动队列管理，集成FQ+PIE，防缓冲区膨胀 |

即时生效，无需重启。内核不支持CAKE时自动降级为FQ-PIE（仍可与BBR配合）。

单独运行：`bash install.sh optimize`

## 证书管理

### 手动续签证书

```bash
python3 /root/singbox-eps-node/scripts/cert_manager.py --renew
```

### 使用Cloudflare API申请15年证书

```bash
python3 /root/singbox-eps-node/scripts/cert_manager.py --cf-cert
```

## CDN 优选 IP（4级降级保障）

1. 本地实测IP池（湖南电信最优）
2. cf.001315.xyz/ct电信API
3. WeTest.vip电信优选DNS
4. IPDB API bestcf

手动更新：`python3 /root/singbox-eps-node/scripts/cdn_monitor.py`

## 流量统计

- 首页查看：`https://{域名}:2087/`
- API接口：`https://{域名}:2087/api/traffic`
- 重置规则：每月14号自动归零

## Hysteria2 端口跳跃

重启后规则自动恢复。手动保存：
```bash
netfilter-persistent save
```

## 健康检查

每5分钟自动运行，检查端口/服务/订阅/防火墙/证书/磁盘。

手动运行：`bash /root/singbox-eps-node/scripts/health_check.sh`

## Telegram 机器人

在.env中配置 `TG_BOT_TOKEN` 和 `TG_ADMIN_CHAT_ID` 后启动：

可用命令：`/状态` `/续签` `/订阅` `/重启` `/优选` `/设置住宅` `/删除住宅`

## 卸载

```bash
systemctl stop singbox singbox-sub singbox-cdn
systemctl disable singbox singbox-sub singbox-cdn
rm /etc/systemd/system/singbox*.service
rm /etc/systemd/system/cake-qdisc*.service
rm /etc/systemd/system/fq-pie-qdisc*.service
systemctl daemon-reload
rm -rf /root/singbox-eps-node
netfilter-persistent save
```
