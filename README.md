# Singbox Manager 使用文档

## 目录
1. [版本说明](#版本说明)
2. [使用说明](#使用说明)
3. [技术指南](#技术指南)
4. [Bug修复记录](#bug修复记录)

---

## 版本说明

### v1.0.2 (2026-04-19)
**更新内容：**
- 简化订阅服务，只保留一个订阅链接
- 订阅包含全部4个节点，由客户端自动选择

### v1.0.1 (2026-04-19)
**更新内容：**
- 新增自动卸载旧面板功能（S-UI、X-UI、Maro等）
- Reality协议使用苹果域名（www.apple.com）伪装
- Hysteria2增加TCP跳跃（salamander混淆）
- 自签证书有效期延长至365天（长期有效）

**修复问题：**
- 修复之前安装脚本会与旧面板冲突的问题
- 修复Reality协议伪装配置错误

### v1.0.0 (2026-04-18)
**初始版本**
- 基于Singbox内核
- 支持4种协议：VLESS Reality、VLESS WS、Trojan WS、Hysteria2
- CDN优选IP自动监控
- 自签证书自动续签

---

## 使用说明

### 一键安装

```bash
wget -O singbox-install.sh https://your-repo/singbox-manager/install.sh
chmod +x singbox-install.sh
./singbox-install.sh
```

安装脚本会自动：
1. 卸载旧面板（S-UI、X-UI等）
2. 安装Singbox内核
3. 配置4种协议的节点
4. 启动所有服务

### 服务管理

```bash
# 查看服务状态
systemctl status singbox

# 重启Singbox
systemctl restart singbox

# 重启订阅服务
systemctl restart singbox-sub

# 重启CDN监控
systemctl restart singbox-cdn

# 查看CDN监控日志
journalctl -u singbox-cdn -f

# 手动续签证书
python3 /root/singbox-manager/scripts/cert_manager.py --renew
```

### 订阅链接

```
http://服务器IP:2096/sub
```

这个订阅链接包含全部4个节点：
- VLESS Reality（苹果域名伪装）
- VLESS WS（Cloudflare CDN）
- Trojan WS（Cloudflare CDN）
- Hysteria2（TCP跳跃）

客户端（如Clash、V2RayN）导入后，会根据策略自动选择最优节点。

### 配置文件位置

| 文件 | 路径 |
|-----|-----|
| 主配置 | /root/singbox-manager/config.json |
| 环境变量 | /root/singbox-manager/.env |
| 证书目录 | /root/singbox-manager/cert/ |
| 管理脚本 | /root/singbox-manager/scripts/ |

---

## 技术指南

### 协议配置详解

#### 1. VLESS Reality
- **端口**: 443
- **伪装**: www.apple.com
- **特点**: 真正的墙外流量特征，难以被识别
- **允许不安全**: 是
- **适用场景**: 最高稳定性要求

```json
{
    "type": "vless",
    "tag": "vless-reality",
    "listen_port": 443,
    "users": [{"id": "UUID", "flow": "xtls-rprx-vision"}],
    "tls": {
        "server_name": "www.apple.com",
        "reality": {
            "enabled": true,
            "handshake": {"server": "www.apple.com", "server_port": 443},
            "private_key": "密钥",
            "short_id": ["abcd1234"]
        }
    }
}
```

#### 2. VLESS WS (CDN)
- **端口**: 8443
- **路径**: /vless-ws
- **CDN**: Cloudflare
- **适用场景**: 速度优先

#### 3. Trojan WS (CDN)
- **端口**: 8444
- **路径**: /trojan-ws
- **CDN**: Cloudflare
- **适用场景**: 兼容性好

#### 4. Hysteria2
- **端口**: 4433
- **混淆**: salamander (TCP跳跃)
- **特点**: 高速下载，适合大流量
- **允许不安全**: 是

### CDN优选IP机制

CDN监控服务每小时自动：
1. 从 api.uouin.com/cloudflare.html 获取优选IP列表
2. 随机选择2个IP分配给VLESS-WS和Trojan-WS
3. 保存到数据库

```python
# 获取优选IP
vless_cdn_ip, trojan_cdn_ip = get_cdn_ips()
```

### 证书管理

- 自签证书有效期：**365天**（长期有效）
- 每天自动检查是否需要续签
- 剩余30天以下会触发续签
- 续签后自动重启Singbox

---

## Bug修复记录

### v1.0.2 修复

| Bug | 问题描述 | 修复方案 |
|-----|---------|---------|
| #005 | 多余的分流订阅链接 | 简化为单一订阅链接 |

### v1.0.1 修复

| Bug | 问题描述 | 修复方案 |
|-----|---------|---------|
| #001 | 旧面板冲突 | 添加 uninstall_old_panels() 函数 |
| #002 | Reality伪装苹果域名 | 将 server_name 改为 www.apple.com |
| #003 | Hysteria2缺少混淆 | 添加 salamander obfs 配置 |
| #004 | 证书有效期过短 | 改为365天长期有效 |

---

## 常见问题

### Q: 安装后无法连接？
A: 检查Singbox状态：`systemctl status singbox`，查看日志：`journalctl -u singbox -n 50`

### Q: 订阅链接打不开？
A: 检查订阅服务：`systemctl status singbox-sub`，端口是否被占用：`netstat -tlnp | grep 2096`

### Q: CDN IP不生效？
A: 手动运行一次CDN监控：`python3 /root/singbox-manager/scripts/cdn_monitor.py`

### Q: 如何完全卸载？
```bash
systemctl stop singbox singbox-sub singbox-cdn
systemctl disable singbox singbox-sub singbox-cdn
rm -rf /root/singbox-manager
rm -f /etc/systemd/system/singbox*.service
systemctl daemon-reload
```

---

**最后更新: 2026-04-19**
