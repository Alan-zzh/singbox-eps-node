# Singbox EPS Node 项目快照

**版本**: v4.14.0 | **更新**: 2026-06-27

---

## 当前状态

### 服务状态
| 服务 | 状态 | 说明 |
|------|------|------|
| singbox | 运行中 | 代理内核，6个入站协议（v4.14.0 精简） |
| singbox-sub | 运行中 | HTTPS订阅服务，端口2087，按 UA 自动识别客户端能力 |
| singbox-cdn | 运行中 | CDN优选IP学习系统 |

### 核心功能
- **6个代理协议**（v4.14.0 精简 7→6）：VLESS-Reality, VLESS-gRPC, Trojan-TCP, VLESS-WS, Trojan-WS, anyTLS
  - 删除：VLESS-HTTPUpgrade（故障最多+兼容最窄）、TUIC v5（UDP易被封+QUIC被QoS）
  - 新增：anyTLS（sing-box 1.12+ 原生，端口 2096，缓解 TLS-in-TLS 指纹）
- **多客户端兼容**（v4.14.0 更新）：`/sub` 默认返回 6 节点，Clash/sing-box/NekoBox/v2rayN/v2rayNG/Shadowrocket 都拿完整订阅；`?client=full` 与 `?client=standard` 等同（HTTPUpgrade/TUIC 已下线，无差别），保留 `standard` 参数兼容旧客户端
- **CDN节点命名统一**（v4.12.2）：Base64 / Clash / sing-box 三类订阅中 CDN 节点统一显示 `-CDN` 后缀
- **流量查询**（v4.12.10 更新）：`/info` 端点（v2rayN 也能看）+ `/api/traffic` JSON + `subscription-userinfo` header；Base64 正文只放节点 URI，分享链接节点名已 URL 编码
- **流量统计修复**（v4.12.2）：iptables INPUT 按 `dpt` + OUTPUT 按 `spt` 双向计数，UDP 端口（TUIC）独立统计；每月14号更新数据库 baseline，不清零内核计数器
- CDN三模式优选：CDN_MODE（ip_optimized/domain_optimized/domain_default）
- Cloudflare 订阅入口 TLS 兼容：`min_tls_version=1.2`，由 `cloudflare_proxy_rules.py apply` 和 `health_check.sh` 自愈维护
- CDN多维度评分（v4.12.5 更新）：用户本地实测投喂/运营商匹配源提权，VPS侧测速只作为辅助；Top3 优先保留真实最优，之后再做 C 段分散
- CDN优选迟滞防抖（v4.12.13 新增）：`get_cdn_ip_for_protocol()` 新 IP 评分必须比当前高 15% 才触发切换，避免频繁切换加剧封禁
- CDN用户路径HTTP测速（v4.12.13 新增）：`test_user_path_latency()` 新增通过代理入口端口(2087)的 HTTP `/info` 测速，取 TLS 握手和 HTTP 延迟中较小值
- CDN故障切换状态查询（v4.12.13 新增）：`/api/cdn-status` 启用 `CdnFailoverController` 状态查询（冷却池、切换计数、上次切换时间）
- Cloudflare 代理入口规则自愈（v4.12.7 更新）：`cloudflare_proxy_rules.py` 按 `jp/sg/hk.290372913.xyz` + 代理端口/路径维护 Rulesets API skip 规则，不绑定用户公网 IP；`health_check.sh` 每 15 分钟确认目标态
- Clash 订阅/CDN 入口恢复（v4.12.20 更新，v4.13.1 标注为兜底降级）：Cloudflare skip 规则覆盖 firewall_managed/sbfm/ratelimit 三个阶段（不含ddos_l7），ddos_l7 phase 创建 `sensitivity_level=eoff` override 放行代理端口流量。⚠️ 此配置仅作为 CF 代理路径的兜底降级，**订阅端点主路径已改为 sub-* 直连**（见下条），不能仅依赖 eoff
- **订阅端点 sub-* 直连绕过 CF DDoS L7（v4.13.1 新增，v4.13.3 代码层补全）**：CF 免费计划 DDoS L7 ML 系统无法通过 API 完全关闭（v4.12.20 的 eoff 方案是假阳性），订阅端点改走 `sub-jp/sub-sg/sub-hk.290372913.xyz` 三个 gray cloud(`proxied=false`)子域名直连源站，完全绕过 CF 代理层。`cert_manager.py` 的 SAN 同时包含主域名+sub-* 子域名。`config.py` 的 `get_sub_domain()` 和 `subscription_service.py` 首页订阅链接+三端点 `profile-web-page-url` header 全部使用 sub-* 子域名。3轮108项+15项验证全部PASS。
- CDN优选评分修复（v4.12.21 更新）：`assign_and_save_ips()` 修复漏传 `user_path_result` 和 `cross_isp_score` 参数的bug，CDN IP评分从83分恢复到95-96分；HK服务器USER_DDNS_DOMAIN修复为zzpzgroup.com
- 本机私有 `deploy.py` 已同步 `scripts/cdn_monitor.py`、`scripts/cloudflare_proxy_rules.py`、`scripts/health_check.sh` 到 `/opt` 与 `/root` 双运行目录，并在同步后重启 `singbox-cdn`、确认 Cloudflare 规则；该脚本被 `.gitignore` 忽略且不纳入 Git
- CDN IP自动同步：cdn_monitor写数据库+信号文件 → subscription_service检测信号清缓存
- 用户投喂IP池：config.py的CDN_PREFERRED_IPS为真理来源，优先级最高；v4.12.5 新增 9 个用户本地实测优质 IP
- 按月流量统计：iptables内核级 INPUT+OUTPUT 双向计数器，每月14号由订阅服务更新 baseline
- BBRv3+FQ 网络加速（`install.sh optimize` 安装 XanMod BBRv3 内核；首次启用需重启）
- 三层自愈机制：systemd ExecStartPre + health_check.sh（v4.10.20 升级为详细日志版） + StartLimitBurst
- 一键诊断脚本：diagnose.sh 18项检查
- SQLite WAL 模式：多进程并发读写零阻塞（v4.10.20）
- Reality 强随机 short_id：openssl rand -hex 8 生成，禁止 abcd1234 弱预设
- TLS ALPN: ["h2", "http/1.1"] 启用 HTTP/2 多路复用
- 随机端口配置：VLESS-gRPC/Trojan-TCP 端口首次安装随机生成（10000-65535），避免固定端口被识别
- sing-box 版本:1.13.13(SG/HK)/1.13.14(JP);服务端为单独 sing-box,不混装 Xray

### CDN优选IP学习系统
**核心理念：现有IP存活则不换，死亡才替换 + 用户反馈驱动**

**工作流：**
```
每小时自动执行
          ↓
  检查数据库现有CDN IP → TCP存活检测
          ↓
  存活的IP保留 | 死亡的IP标记待替换
          ↓
  收集候选IP（用户投喂+外部API）
          ↓
  从候选池挑存活IP补上死亡空缺
          ↓
  评分排序，写入数据库，更新订阅
```

**优先级排序：**
1. 现有存活IP - 优先保留
2. 用户投喂IP池（CDN_PREFERRED_IPS）- 填补空缺首选
3. 外部API候选 - 按评分排序

### 定时任务
| 任务 | 频率 | 说明 |
|------|------|------|
| health_check.sh | 每15分钟 | 内存/服务/端口/config自愈/磁盘/日志/estab连接告警/iptables/Cloudflare代理入口规则自愈 |
| cert_manager.py --renew | 每月1号凌晨3点 | SSL证书自动续签 |
| subscription_service baseline | 每月14号 00:03 | 更新月度流量基准，不清零 iptables 内核计数器 |

### 路由规则顺序（服务端）
1. 私有地址拒绝（127/8/10/8/172.16/12/192.168/16/fd00::/8/::1/128 → block）
2. final: direct

（注：AI-SOCKS5 智能路由功能已于 v4.10.20 放弃，不再提供 ai-residential 出站。服务端只保留 direct/block 两个出站。）

---

## 目录结构

```
/root/singbox-eps-node/
├── .env                    # 环境变量（所有配置集中管理）
├── .env.example            # 环境变量模板
├── config.json             # singbox配置
├── cert/                   # SSL证书
├── data/
│   ├── singbox.db          # SQLite数据库
│   └── .port_lock          # 端口锁定文件
├── scripts/
│   ├── config.py           # 全局配置（唯一真相源）
│   ├── config_generator.py # sing-box配置生成器
│   ├── subscription_service.py # HTTPS订阅服务
│   ├── cert_manager.py     # 证书管理+HY2端口跳跃
│   ├── cdn_monitor.py      # CDN优选IP监控
│   ├── cloudflare_proxy_rules.py # Cloudflare代理入口规则自愈
│   ├── tg_bot.py           # Telegram机器人
│   ├── logger.py           # 日志管理
│   ├── health_check.sh     # 健康检查（每15分钟）
│   └── diagnose.sh         # 一键诊断脚本
├── deploy/                 # systemd服务文件
├── tests/                  # 测试脚本
├── docs/
│   ├── technical/          # 技术文档
│   ├── plans/              # 计划文档
│   ├── vision/             # 愿景文档
│   ├── reference/          # 参考资料
│   └── archive/            # 归档文档
├── logs/
└── backups/
```

---

## 关键避坑记录

完整避坑记录见 [AGENTS.md](AGENTS.md) 重点禁忌 + [AI_DEBUG_HISTORY.md](AI_DEBUG_HISTORY.md)。

snapshot 仅补充部署相关要点:

1. 修改 subscription_service.py 必须同步修改 config_generator.py(订阅层与服务端层)
2. 修复服务器问题必须同步更新 install.sh(新部署能复现修复)
3. 服务重启必须覆盖所有相关服务:singbox + singbox-sub + singbox-cdn
4. 从 Windows 上传 shell 脚本到 Linux 后必须转换换行符
5. systemd 服务文件中所有路径必须使用绝对路径
6. 守护进程必须加进程锁(fcntl.flock),防止多实例运行
7. singbox 日志必须配 logrotate
8. 禁止硬编码 IP/域名/凭据/路径,统一从 .env 和 config.py 读取

---

## 部署记录

### 新加坡服务器（13.212.37.11）
- 域名：sg.290372913.xyz
- 部署时间：2026-05-04（v4.14.0 更新：2026-06-27）
- 状态：正常运行
- 协议（v4.14.0）：VLESS-Reality, VLESS-gRPC, Trojan-TCP, VLESS-WS-CDN, Trojan-WS-CDN, anyTLS
- vless-grpc 端口: 51263
- trojan-tcp 端口: 14497
- anytls 端口: 2096
- sing-box：1.13.13

### 日本服务器（43.207.152.47）
- 域名：jp.290372913.xyz
- 部署时间：2026-06-26（v4.14.0 更新：2026-06-27）
- 状态：正常运行
- 协议（v4.14.0）：VLESS-Reality, VLESS-gRPC, Trojan-TCP, VLESS-WS-CDN, Trojan-WS-CDN, anyTLS
- vless-grpc 端口: 26359
- trojan-tcp 端口: 56888
- anytls 端口: 2096
- sing-box：1.13.14

### 香港服务器 (43.249.174.222)
- 域名: hk.290372913.xyz
- 系统: Debian 12
- 协议（v4.14.0）: VLESS-Reality, VLESS-gRPC, Trojan-TCP, VLESS-WS-CDN, Trojan-WS-CDN, anyTLS
- 部署时间: 2026-06-04（v4.14.0 更新：2026-06-27）
- vless-grpc 端口: 51794
- trojan-tcp 端口: 65004
- anytls 端口: 2096
- sing-box：1.13.13
