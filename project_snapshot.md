# 项目状态快照 (Project Snapshot)

## 当前版本
**v1.0.12** (HTTPUpgrade协议版)

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

---

## 最新更新内容 (v1.0.12)

### 新增：VLESS-HTTPUpgrade 协议
- **原理**: HTTPUpgrade 是对 HTTP 协议的升级机制，比传统 WebSocket 更轻量，握手过程更简单
- **优势**: 
  - 兼容性：解决了某些 CDN 或反向代理对 WS 支持不完美的问题
  - 性能：在某些高并发场景下，性能表现优于 WS
- **配置**:
  - 端口: 8445
  - 路径: /vless-upgrade
  - 传输: httpupgrade
  - 安全: TLS
- **订阅链接**: 自动生成 `ePS-JP-VLESS-HTTPUpgrade` 节点，使用 CDN IP

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
├── install.sh          # 主安装脚本 (v1.0.12)
├── scripts/
│   ├── config.py       # 配置中心 (从.env读取)
│   ├── config_generator.py  # Singbox配置生成器
│   ├── subscription_service.py  # 订阅服务 (+dotenv+合并订阅)
│   ├── cdn_monitor.py  # CDN监控
│   ├── cert_manager.py # 证书管理 (CF API)
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
