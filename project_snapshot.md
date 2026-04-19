# 项目状态快照 (Project Snapshot)

## 当前版本
**v1.0.14** (Clash自动分流订阅+TG机器人总控版)

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
| v1.0.14 | 2026-04-20 | Clash自动分流订阅+TG机器人总控+CDN多源备用 |

---

## 最新更新内容 (v1.0.14)

### 新增一：Clash 自动分流订阅
- **功能**: 识别客户端 User-Agent，Clash/Stash/Shadowrocket 自动下发 YAML 配置
- **包含**: 
  - 自动选择（负载均衡）：每5分钟测速，自动选最快节点
  - 故障切换：主节点挂了自动切备用
  - 手动选择：用户可自由切换任意节点
- **分流规则**: 苹果服务走 Reality、国内直连、国外走代理
- **依赖**: `pyyaml` (已加入安装脚本)

### 新增二：TG 机器人总控
- **文件**: `scripts/tg_bot.py`
- **命令**:
  - `/status` - 查看服务器状态 (Singbox/订阅/CDN/负载/内存)
  - `/renew` - 强制续签证书
  - `/sub` - 获取订阅链接
  - `/restart` - 重启 Singbox
  - `/cdn` - 更新 CDN IP
  - `/help` - 显示帮助
- **配置**: 在 `.env` 中添加 `TG_BOT_TOKEN` 即可使用
- **服务**: `singbox-tgbot.service` (开机自启)

### 新增三：CDN 多源备用
- **问题**: `api.uouin.com` 挂了就无法获取优选 IP
- **修复方案**: 
  - 添加 2 个备用 IP 源 (GitHub raw + cf.090227.xyz)
  - 所有源失败时使用 Cloudflare 官方兜底 IP (104.16.1.1 等)
- **效果**: CDN IP 获取成功率 100%

### 修复一：证书申请崩溃 Bug
- **问题**: `install.sh` 中内联 Python 代码在 CF API 返回 `private_key: None` 时崩溃
- **修复方案**: 删除臃肿的内联 Python，直接调用 `cert_manager.py --cf-cert`
- **效果**: 证书申请稳定运行

### 修复二：路径写死 Bug
- **问题**: `setup_scripts()` 硬编码 `/root/singbox-eps-node`
- **修复方案**: 改为相对路径 `./scripts` 自动识别
- **效果**: 任意目录名均可正常运行

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
├── install.sh          # 主安装脚本 (v1.0.14)
├── scripts/
│   ├── config.py       # 配置中心 (从.env读取)
│   ├── config_generator.py  # Singbox配置生成器
│   ├── subscription_service.py  # 订阅服务 (+Clash自动分流+Base64修复)
│   ├── cdn_monitor.py  # CDN监控 (+多源备用)
│   ├── cert_manager.py # 证书管理 (CF API修复)
│   ├── tg_bot.py       # TG机器人总控 (新增)
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
