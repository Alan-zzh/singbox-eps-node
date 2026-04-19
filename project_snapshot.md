# 项目状态快照 (Project Snapshot)

## 当前版本
**v1.0.8** (架构纠错版)

---

## 版本历史
| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.0.0 | 2026-04-20 | 初始版本：模块化 Singbox 一键部署面板 |
| v1.0.8 | 2026-04-20 | 修复5个严重Bug：无硬编码/动态密钥/OBFS参数 |

---

## 最新更新内容 (v1.0.8)

### 修复的5个严重Bug：

**Bug 1: Reality密钥缺失 (致命错误)** ✅
- **修复方案**: `install.sh` 的 `generate_env_file()` 函数新增 `singbox generate reality-keypair` 调用
- **验证方式**: 密钥自动写入 `/root/singbox-manager/.env`

**Bug 2: 环境变量文件未初始化 (逻辑断层)** ✅
- **修复方案**: `install.sh` 新增 `generate_env_file()` 函数
- **自动生成**: UUID、密码、Reality密钥等全部动态生成
- **文件位置**: `/root/singbox-manager/.env`

**Bug 3: PIP安装被拦截 (部署阻断)** ✅
- **修复方案**: 改用 `apt-get install python3-flask python3-requests python3-dotenv`
- **备选方案**: `--break-system-packages` 参数

**Bug 4: 硬编码泄露 (通用性极差)** ✅
- **修复文件**:
  - `install.sh`: 移除脚本内硬编码IP/域名
  - `config.py`: 改为从环境变量读取 `SERVER_IP`, `CF_DOMAIN`
  - `subscription_service.py`: 移除默认值 `54.250.149.157`
  - `config_generator.py`: 硬编码域名 `jp1.290372913.xyz` → `cf_domain or server_ip`

**Bug 5: Hysteria2订阅链接缺少obfs参数 (无法连接)** ✅
- **修复方案**: `subscription_service.py` 新增:
  ```python
  'obfs': 'salamander',
  'obfs-password': HYSTERIA2_PASSWORD[:8]
  ```

---

## 核心目录树
```
singbox-eps-node/
├── install.sh          # 主安装脚本 (v1.0.8)
├── scripts/
│   ├── config.py       # 配置中心 (从.env读取)
│   ├── config_generator.py  # Singbox配置生成器
│   ├── subscription_service.py  # 订阅服务
│   ├── cdn_monitor.py  # CDN监控
│   ├── cert_manager.py # 证书管理
│   └── logger.py       # 日志模块
├── docs/
│   └── architecture.md # 架构文档
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
**新仓库**: https://github.com/Alan-zzh/singbox-eps-node-v2

---

## 下一步待办 (Next Steps)
1. ~~修复 Reality 密钥生成~~
2. ~~修复 .env 初始化~~
3. ~~修复 PIP 安装问题~~
4. ~~移除硬编码~~
5. ~~修复 Hysteria2 obfs 参数~~
6. ~~重新上传 GitHub~~
7. 测试完整安装流程
