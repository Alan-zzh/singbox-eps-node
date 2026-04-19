# 项目状态快照 (Project Snapshot)

## 当前版本
**v1.0.13** (Bug修复与优化版)

---

## 版本历史
| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.0.0 | 2026-04-20 | 初始版本：模块化 Singbox 一键部署面板 |
| v1.0.8 | 2026-04-20 | 修复5个严重Bug：无硬编码/动态密钥/OBFS参数 |
| v1.0.9 | 2026-04-20 | 修复 Systemd 环境变量隔离盲区 |
| v1.0.10 | 2026-04-20 | 终极验收：dotenv双保险/CF证书激活 |
| v1.0.11 | 2026-04-20 | 合并订阅/重装系统/非ROOT自动切换 |
| v1.0.12 | 2026-04-20 | 添加 VLESS-HTTPUpgrade 协议 (CDN节点) |
| v1.0.13 | 2026-04-20 | 修复CF证书API/Base64填充/iptables优化/域名提示 |

---

## 最新更新内容 (v1.0.13)

### 修复一：Cloudflare 证书 API 致命错误
- **问题**: 原代码使用错误的参数格式 (`type: origin`, `host: domain`)，CF API 直接返回 400 错误
- **修复方案**: 
  - 先用 `openssl` 本地生成私钥和 CSR
  - 使用正确参数: `hostnames`, `request_type: origin-rsa`, `csr`
  - 私钥在本地生成，不需要 CF 返回
- **效果**: Cloudflare 15年证书申请功能现在可以正常工作

### 修复二：外部订阅合并 Base64 填充炸裂
- **问题**: 很多机场的 Base64 订阅链接结尾不带 `=` 填充符，Python 严格解码会崩溃
- **修复方案**: 增加 Base64 安全补齐逻辑 `padded_raw = raw + '=' * (-len(raw) % 4)`
- **效果**: 合并任何机场订阅都不会再崩溃

### 优化一：iptables 精准清理
- **问题**: `iptables -t nat -F PREROUTING` 会清空所有端口转发规则，影响 Docker 等服务
- **修复方案**: 改为精准清理 `iptables-save | grep -v "DNAT.*4433" | iptables-restore`
- **效果**: 只清理 Hysteria2 相关规则，不影响其他服务

### 优化二：无域名 CDN 提示
- **问题**: 用户没填域名时，CDN 节点会失效但没有提示
- **修复方案**: 安装时检测未配置域名，显示警告提示
- **效果**: 用户明确知道需要配置域名才能使用 CDN 加速

### 当前节点列表 (5个)
| 节点名称 | 协议 | 传输 | 安全 | CDN |
|----------|------|------|------|-----|
| ePS-JP-VLESS-Reality | VLESS | TCP | Reality | 否 |
| ePS-JP-VLESS-WS | VLESS | WebSocket | TLS | 是 |
| ePS-JP-VLESS-HTTPUpgrade | VLESS | HTTPUpgrade | TLS | 是 |
| ePS-JP-Trojan-WS | Trojan | WebSocket | TLS | 是 |
| ePS-JP-Hysteria2 | Hysteria2 | UDP | TLS | 否 |

---

## 核心目录树
```
singbox-eps-node/
├── install.sh          # 主安装脚本 (v1.0.13)
├── scripts/
│   ├── config.py       # 配置中心 (从.env读取)
│   ├── config_generator.py  # Singbox配置生成器
│   ├── subscription_service.py  # 订阅服务 (+dotenv+合并订阅+Base64修复)
│   ├── cdn_monitor.py  # CDN监控
│   ├── cert_manager.py # 证书管理 (CF API修复)
│   └── logger.py       # 日志模块
├── docs/
│   └── architecture.md # 架构文档
├── project_snapshot.md # 项目状态快照
└── .git/
```

---

## 依赖库版本锁定
- Python 3
- Flask (python3-flask)
- python3-dotenv
- python3-requests
- Singbox (最新版本)
- iptables-persistent

---

## 节点配置 (无硬编码)
| 节点 | 协议 | 说明 |
|------|------|------|
| ePS-JP-VLESS-Reality | VLESS+Reality | 殖民节点，苹果域名伪装 |
| ePS-JP-VLESS-WS | VLESS+WebSocket | CDN节点 |
| ePS-JP-Trojan-WS | Trojan+WebSocket | CDN节点 |
| ePS-JP-Hysteria2 | Hysteria2 | 直连节点，端口跳跃 21000-21200 |
| ePS-JP-SOCKS5 | SOCKS5 | 本地代理 (不出订阅) |

---

## GitHub 仓库
**仓库地址**: https://github.com/Alan-zzh/singbox-eps-node-v2

---

## 下一步待办 (Next Steps)
1. ~~修复 Reality 密钥生成~~
2. ~~修复 .env 初始化~~
3. ~~修复 PIP 安装问题~~
4. ~~移除硬编码~~
5. ~~修复 Hysteria2 obfs 参数~~
6. ~~重新上传 GitHub~~
7. ~~修复 Systemd 环境变量隔离~~
8. ~~Python dotenv 双保险~~
9. ~~激活 Cloudflare 15年证书~~
10. 服务器端完整安装测试
