# Singbox EPS Node 使用说明

## 快速开始

### 一键安装

```bash
bash <(curl -sL https://raw.githubusercontent.com/Alan-zzh/singbox-eps-node/main/install.sh)
```

### 安装后配置

1. 编辑环境变量：
```bash
nano /root/singbox-eps-node/.env
```

2. 填写必填项（SERVER_IP留空可自动检测，CF_DOMAIN填写你的域名）

3. 重启服务：
```bash
systemctl restart singbox singbox-sub singbox-cdn
```

### 获取订阅链接

```bash
# 查看订阅地址
cat /root/singbox-eps-node/.env | grep -E "CF_DOMAIN|SERVER_IP|SUB_PORT"
```

订阅地址格式：`https://{域名或IP}:2087/sub/{国家代码}`

## 节点列表

| 节点名称 | 协议 | 用途 | 端口 |
|---------|------|------|------|
| ePS-JP-VLESS-Reality | VLESS + Reality | 直连节点 | 443 |
| ePS-JP-VLESS-WS | VLESS + WebSocket | CDN节点 | 8443 |
| ePS-JP-VLESS-HTTPUpgrade | VLESS + HTTPUpgrade | CDN节点 | 2053 |
| ePS-JP-Trojan-WS | Trojan + WebSocket | CDN节点 | 2083 |
| ePS-JP-Hysteria2 | Hysteria2 + 端口跳跃 | 直连节点 | 443 (跳跃: 21000-21200) |
| AI-SOCKS5 | SOCKS5 | AI流量路由 | 外部端口 |

## 服务管理

### 查看服务状态

```bash
systemctl status singbox        # Singbox内核
systemctl status singbox-sub    # 订阅服务
systemctl status singbox-cdn    # CDN监控
```

### 重启服务

```bash
systemctl restart singbox        # 重启Singbox
systemctl restart singbox-sub    # 重启订阅服务
systemctl restart singbox-cdn    # 重启CDN监控
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
| 数据库 | `/root/singbox-eps-node/data/singbox.db` | CDN IP存储 |
| 健康检查日志 | `/root/singbox-eps-node/logs/` | 健康检查日志 |

## 证书管理

### 手动续签证书

```bash
python3 /root/singbox-eps-node/scripts/cert_manager.py --renew
```

### 使用Cloudflare API申请15年证书

```bash
# 先在.env中配置CF_API_TOKEN
python3 /root/singbox-eps-node/scripts/cert_manager.py --cf-cert
```

### 查看证书状态

```bash
openssl x509 -in /root/singbox-eps-node/cert/cert.crt -noout -dates
```

## CDN 优选 IP

### 手动更新 CDN IP

```bash
python3 /root/singbox-eps-node/scripts/cdn_monitor.py
```

### 查看当前CDN IP

```bash
sqlite3 /root/singbox-eps-node/data/singbox.db "SELECT * FROM cdn_settings"
```

## Hysteria2 端口跳跃

### 查看端口跳跃规则

```bash
iptables -t nat -L PREROUTING -n | grep 443
```

### 重新设置端口跳跃规则

```bash
python3 /root/singbox-eps-node/scripts/cert_manager.py --setup-iptables
```

### 规则持久化

重启后规则自动恢复。如需手动保存：
```bash
netfilter-persistent save
```

## 健康检查

健康检查脚本每5分钟自动运行（通过cron），检查：
- 端口完整性
- 服务状态（自动重启异常服务）
- 订阅接口可用性
- 防火墙状态
- 证书有效期
- 磁盘空间

手动运行：
```bash
bash /root/singbox-eps-node/scripts/health_check.sh
```

## Telegram 机器人

在.env中配置 `TG_BOT_TOKEN` 和 `TG_ADMIN_CHAT_ID` 后启动：

```bash
python3 /root/singbox-eps-node/scripts/tg_bot.py
```

可用命令：
- `/状态` - 查看服务器状态
- `/续签` - 强制续签证书
- `/订阅` - 获取订阅链接
- `/重启` - 重启Singbox
- `/优选` - 更新CDN IP
- `/设置住宅` - 设置AI住宅IP SOCKS5
- `/删除住宅` - 删除AI住宅IP

## 卸载

```bash
systemctl stop singbox singbox-sub singbox-cdn
systemctl disable singbox singbox-sub singbox-cdn
rm /etc/systemd/system/singbox*.service
systemctl daemon-reload
rm -rf /root/singbox-eps-node
iptables -t nat -F PREROUTING
netfilter-persistent save
```

## 常见问题

### Q: 订阅链接打不开？

```bash
systemctl status singbox-sub
ss -tlnp | grep 2087
```

### Q: Hysteria2 连接失败？

```bash
iptables -t nat -L PREROUTING -n | grep 443
```

确保21000-21200端口跳跃规则存在。

### Q: CDN 节点无法连接？

```bash
python3 /root/singbox-eps-node/scripts/cdn_monitor.py
```

### Q: 如何修改节点密码？

编辑 `/root/singbox-eps-node/.env`，修改对应密码后：
```bash
systemctl restart singbox singbox-sub
```
