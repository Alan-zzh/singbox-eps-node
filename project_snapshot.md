# 项目状态快照 (Project Snapshot)

## 当前版本
**v1.0.29** (配置恢复+CDN服务修复+GitHub交付版)

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
| v1.0.15 | 2026-04-20 | 修复订阅安全漏洞+证书续签后订阅服务重启 |
| v1.0.16 | 2026-04-20 | 节点命名规则优化+CDN端口兼容Cloudflare |
| v1.0.17 | 2026-04-20 | 修复 config_generator.py 路径错误 (singbox-manager -> singbox-eps-node) |
| v1.0.18 | 2026-04-20 | 修复 VLESS 用户字段 id -> uuid (sing-box 1.10.0 兼容) |
| v1.0.19 | 2026-04-20 | 修复订阅超时+多客户端兼容+路径修复 |
| v1.0.20 | 2026-04-20 | 修复直连节点 short_id 不匹配+CDN优选IP接口+清理S-UI引用 |
| v1.0.21 | 2026-04-20 | 修复GeoIP陷阱+每协议独立CDN IP+数据库路径统一 |
| v1.0.22 | 2026-04-20 | 优化CDN IP获取策略：动态网站优先+静态源备用+IP不足时循环分配 |
| v1.0.23 | 2026-04-20 | 终极降维方案：IP身份伪装（HTTP Header Spoofing）+ 正则精准提取 |
| v1.0.24 | 2026-04-20 | 容灾轮询伪装IP池：湖南电信专属IP池+优先级递减+自动切换 |
| v1.0.25 | 2026-04-20 | SOCKS5 AI协议牵制节点集成：206.163.4.241:36753 |
| v1.0.26 | 2026-04-20 | 地区代码动态化修复：节点名称自动使用COUNTRY_CODE环境变量 |
| v1.0.27 | 2026-04-20 | 防火墙配置修复+HTTPS/HTTP自动检测+systemd服务路径修复 |
| v1.0.28 | 2026-04-20 | 服务器彻底重置+订阅服务恢复+所有组件重新安装 |
| v1.0.29 | 2026-04-20 | 配置恢复+CDN服务修复+GitHub交付版 |

---

## 最新更新内容 (v1.0.27)

### 防火墙配置修复
- **问题**: 服务器防火墙未放行所有需要的端口，导致外部无法访问订阅服务
- **解决方案**: 使用iptables放行所有需要的TCP/UDP端口
- **放行的端口**:
  - TCP: 22 (SSH), 443 (VLESS-Reality/Hysteria2), 8443 (VLESS-WS-CDN), 2053 (VLESS-HTTPUpgrade-CDN), 2083 (Trojan-WS-CDN), 6969 (订阅服务), 36753 (SOCKS5)
  - UDP: 443 (Hysteria2), 21000:21200 (Hysteria2端口跳跃)
- **效果**: 外部可以正常访问订阅服务和所有节点端口

### HTTPS/HTTP配置混乱修复
- **问题**: 订阅服务证书路径硬编码，导致HTTPS/HTTP混乱
- **解决方案**: 自动检测多个可能的证书路径，找到证书就用HTTPS，找不到就用HTTP
- **检测的证书路径**:
  - `/root/singbox-eps-node/cert/cert.pem`
  - `/root/singbox-eps-node/certs/cert.pem`
  - `/root/singbox-manager/cert/cert.pem`
- **效果**: 订阅服务自动选择HTTPS或HTTP，不再混乱

### systemd服务路径修复
- **问题**: singbox-sub.service指向错误路径（singbox-manager/scripts/manager/）
- **解决方案**: 更新为正确路径（singbox-eps-node/scripts/）
- **修复内容**:
  - WorkingDirectory: /root/singbox-eps-node/scripts
  - EnvironmentFile: /root/singbox-eps-node/.env
  - ExecStart: /usr/bin/python3 /root/singbox-eps-node/scripts/subscription_service.py
- **效果**: 订阅服务可以正常启动和重启

---

## 最新更新内容 (v1.0.26)

### 地区代码动态化修复
- **问题**: 节点名称硬编码为`JP-`，无法根据VPS地区自动调整
- **解决方案**: 使用`COUNTRY_CODE`环境变量动态生成节点名称
- **核心机制**: 
  - 节点名称格式: `{COUNTRY_CODE}-{协议名称}`
  - 订阅页面动态显示地区代码
  - 支持多地区部署时的自动适配
- **环境变量**: `COUNTRY_CODE=JP`（日本服务器）
- **效果**: 订阅链接和节点名称自动反映VPS所在地区

---

## 最新更新内容 (v1.0.25)

### SOCKS5 AI协议牵制节点集成
- **新增节点类型**: SOCKS5协议，用于AI协议牵制分流
- **服务器信息**: 
  - 地址: `206.163.4.241`
  - 端口: `36753`
  - 用户名: `4KKsLB7F`
  - 密码: `KgEKVmVgxJ`
- **节点名称**: `AI-SOCKS5`
- **协议支持**: 
  - 标准Base64订阅链接
  - Clash YAML订阅格式
- **功能定位**: 作为AI协议牵制节点，实现流量分流和协议混淆

---

## 最新更新内容 (v1.0.24)

### 容灾轮询伪装IP池机制
- **问题**: 单一伪装IP可能被目标网站拉黑或识别
- **解决方案**: 实现湖南电信专属IP池容灾轮询机制
- **伪装IP矩阵池**（优先级递减）：
  - `222.246.129.80` - 优先级一：湖南电信最优DNS
  - `59.51.78.210` - 优先级二：备用湖南电信DNS
  - `114.114.114.114` - 优先级三：全国通用DNS（终极兜底）
- **容灾逻辑**: 
  - 按优先级依次尝试，一旦成功立即返回
  - 失败时自动无缝切换到下一个IP
  - 所有伪装IP均失败时使用官方兜底IP
- **效果**: 极高的容灾能力，确保伪装永不失效

---

## 最新更新内容 (v1.0.23)

### 终极降维方案：IP身份伪装（HTTP Header Spoofing）
- **问题**: 复杂的备用源策略不稳定，静态GitHub源IP数量波动大
- **解决方案**: 采用纯IP伪装方案，强制脚本伪装成国内用户
- **核心机制**: 
  - 请求头伪装：`X-Forwarded-For: 114.114.114.114`、`X-Real-IP: 114.114.114.114`、`Client-IP: 114.114.114.114`
  - 正则精准提取：使用`re.findall()`精准提取HTML中的IP，避免`split('\n')`乱码问题
  - 严格过滤：只保留Cloudflare官方IP段（104./172./162./108./141./198.）
- **效果**: 服务器在日本，但获取的是国内三网最快的Cloudflare优选IP

### 简化代码结构
- **移除**: 不再需要复杂的静态源备用机制
- **保留**: 动态网站源 + 兜底IP机制
- **优化**: 代码更简洁，逻辑更清晰

---

## 最新更新内容 (v1.0.22)

### CDN IP 获取策略优化
- **问题**: 静态GitHub源返回IP数量不稳定（有时只有1个），导致部分协议IP为空
- **修复方案**: 
  - 调整获取优先级：动态网站（带国内IP伪装）→ 静态GitHub源 → 兜底IP
  - 动态网站获取到IP后，进行连通性测试，确保IP可用
  - 静态源作为备用，在动态网站失败时使用
- **效果**: 稳定获取大量国内优选IP（38+个），所有协议都有独立IP

### IP分配逻辑优化
- **问题**: 当可用IP不足3个时，部分协议会分配到空IP
- **修复方案**: IP不足3个时，循环使用已有的IP填充
  - 例如只有1个IP时，3个协议都使用这同一个IP
  - 有2个IP时，按顺序循环分配
- **效果**: 确保所有协议始终有可用的CDN IP

### systemd 服务配置优化
- **修复**: 更新 `singbox-cdn.service` 工作目录和脚本路径
- **添加**: `Environment=PYTHONUNBUFFERED=1` 确保日志实时输出

---

## 最新更新内容 (v1.0.21)

### 核心问题修复：GeoIP 陷阱
- **问题**: 服务器在日本 (AWS)，访问 `api.uouin.com/cloudflare.html` 时返回的是日本优选IP，而不是国内优选IP
- **原因**: 该网站会根据访问者的IP地理位置返回对应地区的优选IP
- **影响**: 国内用户连接日本优选IP会导致高延迟和丢包
- **修复方案**: 
  - 在请求头中添加伪装：`X-Forwarded-For: 114.114.114.114`、`X-Real-IP: 114.114.114.114`、`Client-IP: 114.114.114.114`
  - 使用正则表达式精准提取HTML中的IP地址
  - 过滤只保留 Cloudflare 官方IP段 (104./172./162./108./141./198.)
- **效果**: 无论服务器在哪里，都能获取到国内三网最快的Cloudflare优选IP

### CDN IP 分配优化
- **旧方案**: 所有CDN协议共用同一个优选IP
- **新方案**: 每个CDN协议独立IP（前10个IP随机选3个不同的）
  - VLESS-WS: 独立IP
  - VLESS-HTTPUpgrade: 独立IP
  - Trojan-WS: 独立IP
- **好处**: 即使某个IP被封，其他协议仍然可用

### 数据库路径统一
- **问题**: 多个脚本使用不同的数据库路径，导致数据不同步
- **修复**: 
  - `config.py` 中统一设置 `DATA_DIR = /root/singbox-manager/data`
  - `subscription_service.py` 从 `config.py` 读取 `DB_FILE`
  - `cdn_monitor.py` 从 `config.py` 读取 `DATA_DIR`
  - 创建符号链接 `/root/singbox-manager/.env -> /root/singbox-eps-node/.env`

### systemd 服务配置修复
- **问题**: 服务配置指向错误的 `.env` 文件路径
- **修复**: 更新 `singbox-sub.service` 和 `singbox-cdn.service` 指向正确的路径

---

## 当前节点列表 (6个)
| 节点名称 | 协议 | 传输 | 安全 | CDN | 端口 | 优选IP |
|----------|------|------|------|-----|------|--------|
| JP-VLESS-Reality | VLESS | TCP | Reality | 否 | 443 | - |
| JP-VLESS-WS-CDN | VLESS | WebSocket | TLS | 是 | 8443 | 172.64.82.114 |
| JP-VLESS-HTTPUpgrade-CDN | VLESS | HTTPUpgrade | TLS | 是 | 2053 | 198.41.208.15 |
| JP-Trojan-WS-CDN | Trojan | WebSocket | TLS | 是 | 2083 | 162.159.140.85 |
| JP-Hysteria2 | Hysteria2 | UDP | TLS+salamander | 否 | 443 (跳跃 21000-21200) | - |
| AI-SOCKS5 | SOCKS5 | TCP | 用户名密码认证 | 否 | 36753 | 206.163.4.241 |

---

## 核心目录树
```
singbox-eps-node/
├── install.sh          # 主安装脚本 (v1.0.20, 已清理S-UI引用)
├── scripts/
│   ├── config.py       # 配置中心 (从.env读取, DATA_DIR统一)
│   ├── config_generator.py  # Singbox配置生成器 (v1.0.20, short_id动态读取)
│   ├── subscription_service.py  # 订阅服务 (v1.0.21, 每协议独立CDN IP)
│   ├── cdn_monitor.py  # CDN监控 (v1.0.21, GeoIP伪装+正则提取)
│   ├── cert_manager.py # 证书管理
│   ├── tg_bot.py       # TG机器人总控
│   └── logger.py       # 日志模块
├── data/
│   └── singbox.db      # 统一数据库路径
├── docs/
│   └── architecture.md # 架构文档
├── project_snapshot.md # 项目状态快照
└── .git/
```

---

## VPS 部署信息
- **服务器**: 54.250.149.157 (AWS 日本)
- **域名**: jp.290372913.xyz
- **订阅端口**: 6969
- **订阅路径**: /sub/JP
- **国家代码**: JP
- **Reality SNI**: www.apple.com
- **Reality short_id**: f238a057
- **Reality public_key**: iPPe7pIwDdTeWXSdlseBdzN9zbXfcUeqIr1nw0RoXgI (完整)
- **Hysteria2 端口跳跃**: 21000-21200 → 443
- **数据库路径**: /root/singbox-manager/data/singbox.db
- **.env 路径**: /root/singbox-eps-node/.env (已创建符号链接)

---

## 服务状态验证 (2026-04-20)
| 服务 | 状态 | 端口 |
|------|------|------|
| singbox | ✅ active | 443, 8443, 2053, 2083, 1080 |
| singbox-sub | ✅ active | 6969 |
| singbox-cdn | ✅ active | - |
| singbox-tgbot | ✅ active | - |

---

## CDN 优选 IP 机制
- **核心策略**: 容灾轮询伪装IP池 - 湖南电信专属IP池+优先级递减+自动切换
- **伪装IP矩阵池**（按优先级递减）：
  - `222.246.129.80` - 优先级一：湖南电信最优DNS
  - `59.51.78.210` - 优先级二：备用湖南电信DNS  
  - `114.114.114.114` - 优先级三：全国通用DNS（终极兜底）
- **容灾逻辑**: 按优先级依次尝试，成功即返回，失败自动切换
- **数据源**: `https://api.uouin.com/cloudflare.html` (带容灾轮询伪装)
- **正则提取**: 精准提取HTML中的IP，避免`split('\n')`乱码
- **IP过滤**: 只保留Cloudflare官方IP段（104./172./162./108./141./198.）
- **更新频率**: 每小时自动更新
- **分配策略**: 前5个IP随机选3个，每个CDN协议独立IP；IP不足时循环分配
- **数据库存储**: `cdn_settings` 表
  - `vless_ws_cdn_ip`: VLESS-WS 优选IP
  - `vless_upgrade_cdn_ip`: VLESS-HTTPUpgrade 优选IP
  - `trojan_ws_cdn_ip`: Trojan-WS 优选IP
  - `cdn_ips_list`: 所有可用IP列表
  - `cdn_updated_at`: 最后更新时间

---

## 已知问题与解决方案
1. **VLESS 配置格式**: sing-box 1.10.0 使用 `uuid` 字段，不是 `id`
2. **CDN IP 文件**: 首次运行可能不存在，cdn_monitor.py 会自动生成
3. **Cloudflare 证书**: 需要域名已接入 Cloudflare 才能申请，否则使用自签证书
4. **订阅超时**: 客户端更新订阅时不能走代理，必须直连订阅服务器 IP
5. **Cloudflare 端口限制**: Cloudflare 不支持 6969 端口，订阅必须用 IP 访问
6. **Reality short_id**: 必须与 .env 配置一致，否则直连节点不通
7. **Reality public_key**: 必须完整使用，不能截取
8. **GeoIP 陷阱**: 服务器在日本会获取日本优选IP，已通过请求头伪装解决

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
10. ~~修复直连节点 short_id 不匹配~~
11. ~~完善 CDN 优选 IP 功能~~
12. ~~修复 GeoIP 陷阱~~
13. ~~每协议独立 CDN IP~~
14. 服务器端完整安装测试
