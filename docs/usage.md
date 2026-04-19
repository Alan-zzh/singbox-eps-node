# Singbox Manager 使用说明

## 快速开始

### 一键安装

```bash
wget -O install.sh https://your-domain.com/install.sh
chmod +x install.sh
./install.sh
```

### 安装后信息

- **订阅链接**: `https://服务器IP:2096/sub`
- **节点数量**: 4 个（包含在订阅中）
- **SOCKS5 代理**: 端口 1080（不在订阅中）

## 节点列表

| 节点名称 | 协议 | 用途 | 端口 |
|---------|------|------|------|
| ePS-JP-VLESS-Reality | VLESS + Reality | 殖民节点 | 443 |
| ePS-JP-VLESS-WS | VLESS + WebSocket | CDN 节点 | 8443 |
| ePS-JP-Trojan-WS | Trojan + WebSocket | CDN 节点 | 8444 |
| ePS-JP-Hysteria2 | Hysteria2 + 端口跳跃 | CDN 节点 | 4433 (跳跃端口: 4434-4450) |
| ePS-JP-SOCKS5 | SOCKS5 | 本地代理 | 1080 |

## 服务管理

### 查看服务状态

```bash
systemctl status singbox        # Singbox 内核
systemctl status singbox-sub    # 订阅服务
systemctl status singbox-cdn    # CDN 监控
```

### 重启服务

```bash
systemctl restart singbox        # 重启 Singbox
systemctl restart singbox-sub     # 重启订阅服务
systemctl restart singbox-cdn    # 重启 CDN 监控
```

### 查看日志

```bash
tail -f /var/log/singbox.log
journalctl -u singbox -f
```

## 配置文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| Singbox 配置 | `/root/singbox-manager/config.json` | Singbox 主配置 |
| 证书 | `/root/singbox-manager/cert/cert.crt` | 自签名证书 |
| 私钥 | `/root/singbox-manager/cert/cert.key` | 证书私钥 |
| 数据库 | `/root/singbox-manager/singbox.db` | CDN IP 存储 |
| 环境变量 | `/root/singbox-manager/.env` | 密码和密钥 |

## 证书管理

### 手动续签证书

```bash
python3 /root/singbox-manager/scripts/cert_manager.py --renew
```

### 查看证书状态

```bash
openssl x509 -in /root/singbox-manager/cert/cert.crt -noout -dates
```

## CDN 优选 IP

### 手动更新 CDN IP

```bash
python3 /root/singbox-manager/scripts/cdn_monitor.py
```

### 守护进程模式

CDN 监控默认以守护进程运行，每 3600 秒更新一次。

查看进程：
```bash
ps aux | grep cdn_monitor
```

## Hysteria2 端口跳跃

### 原理

客户端连接到 4434-4450 中的随机端口，iptables 将请求转发到 4433。

### 查看端口跳跃规则

```bash
iptables -t nat -L PREROUTING -n | grep 443
```

### 规则持久化

重启后规则自动恢复，无需手动操作。

如果需要重新保存规则：
```bash
netfilter-persistent save
```

## 卸载

```bash
# 停止所有服务
systemctl stop singbox singbox-sub singbox-cdn

# 禁用服务
systemctl disable singbox singbox-sub singbox-cdn

# 删除服务文件
rm /etc/systemd/system/singbox*.service
systemctl daemon-reload

# 删除目录
rm -rf /root/singbox-manager

# 清理 iptables 规则
iptables -t nat -F PREROUTING
netfilter-persistent save
```

## 常见问题

### Q: 订阅链接打不开？

检查订阅服务状态：
```bash
systemctl status singbox-sub
```

检查端口是否开放：
```bash
netstat -tlnp | grep 2096
```

### Q: Hysteria2 连接失败？

检查端口跳跃规则：
```bash
iptables -t nat -L PREROUTING -n | grep 4433
```

确保 4434-4450 端口已开放。

### Q: CDN 节点无法连接？

手动更新 CDN IP：
```bash
python3 /root/singbox-manager/scripts/cdn_monitor.py
```

### Q: 如何修改节点密码？

编辑 `/root/singbox-manager/.env` 文件，修改对应密码后重启：
```bash
systemctl restart singbox singbox-sub
```

## 更新日志

### v1.0.4 (2026-04-20)
- 模块化架构优化
- 统一配置、日志、错误处理
- 添加文档（架构设计、使用说明）
- Hysteria2 端口跳跃 iptables 持久化

### v1.0.3
- 添加 SOCKS5 协议
- CDN 优选 IP 随机分配
- Reality 协议支持
- 自签名证书自动续签
