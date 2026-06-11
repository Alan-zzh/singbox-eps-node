# Singbox EPS Node 项目快照

**版本**: v4.12.1 | **更新**: 2026-06-11

---

## 当前状态

### 服务状态
| 服务 | 状态 | 说明 |
|------|------|------|
| singbox | 运行中 | 代理内核，7个入站协议 |
| singbox-sub | 运行中 | HTTPS订阅服务，端口2087，按 UA 自动识别客户端能力 |
| singbox-cdn | 运行中 | CDN优选IP学习系统 |

### 核心功能
- **7个代理协议**：VLESS-Reality, VLESS-gRPC, Trojan-TCP, VLESS-WS, VLESS-HTTPUpgrade, Trojan-WS, TUIC v5
- **多客户端兼容**（v4.12.1 新增）：UA 自动识别客户端能力，Clash/sing-box/NekoBox → 7 节点；v2rayN/v2rayNG/Shadowrocket/Quantumult X → 5 节点（剔除 HTTPUpgrade + TUIC v5）
- **流量查询**（v4.12.1 新增）：`/info` 端点（v2rayN 也能看）+ `/api/traffic` JSON + 订阅 Base64 头部插入流量注释
- **流量统计修复**（v4.12.1）：iptables INPUT + OUTPUT 双向计数，UDP 端口（TUIC）独立统计
- CDN三模式优选：CDN_MODE（ip_optimized/domain_optimized/domain_default）
- CDN多维度评分（v4.10.20 精简）：用户路径(70%) + VPS侧(20%) + 三网均衡(5%) + 稳定性(5%)。已废除 google_latency/google_speed 两个无效维度，数据库列已 DROP
- CDN IP自动同步：cdn_monitor写数据库+信号文件 → subscription_service检测信号清缓存
- 用户投喂IP池：config.py的CDN_PREFERRED_IPS为真理来源，优先级最高
- 按月流量统计：iptables内核级 INPUT+OUTPUT 双向计数器，每月14号cron自动归零
- BBR+FQ 网络加速
- TCP Fast Open 优化：所有入站/出站启用 `tcp_fast_open: true`，降低连接延迟 30-50ms
- 三层自愈机制：systemd ExecStartPre + health_check.sh（v4.10.20 升级为详细日志版） + StartLimitBurst
- 一键诊断脚本：diagnose.sh 18项检查
- SQLite WAL 模式：多进程并发读写零阻塞（v4.10.20）
- Reality 强随机 short_id：openssl rand -hex 8 生成，禁止 abcd1234 弱预设
- TLS ALPN: ["h2", "http/1.1"] 启用 HTTP/2 多路复用
- 随机端口配置：VLESS-gRPC/Trojan-TCP 端口首次安装随机生成（10000-65535），避免固定端口被识别
- sing-box 版本：1.15.0（v4.11.0 升级）

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
| health_check.sh | 每15分钟 | 内存/服务/端口/config自愈/磁盘/日志/estab连接告警/iptables 完整 8 项 |
| cert_manager.py --renew | 每月1号凌晨3点 | SSL证书自动续签 |
| iptables -Z INPUT/OUTPUT | 每月3号 00:03 | 流量计数器月度归零 |

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

1. DNS服务器detour必须为direct，不能走代理
2. ~~AI规则禁止包含通用域名如google.com~~ (AI-SOCKS5 路由 v4.10.20 已废除)
3. ~~排除规则必须在AI规则之前~~ (AI 路由已废除，无相关排除规则)
4. 修改subscription_service.py必须同步修改config_generator.py
5. 修复服务器问题必须同步更新install.sh
6. 服务重启必须覆盖所有相关服务：singbox + singbox-sub + singbox-cdn
7. 数据库连接必须在finally中关闭
8. 414MB小内存VPS必须配Swap（2GB）+ MemoryMin + GOMEMLIMIT
9. singbox日志必须配logrotate
10. 禁止硬编码IP/域名/凭据/路径，统一从.env和config.py读取（v4.10.20 复查通过：仓库内已无明文密码）
11. 从Windows上传shell脚本到Linux后必须转换换行符
12. systemd服务文件中所有路径必须使用绝对路径
13. 守护进程必须加进程锁（fcntl.flock），防止多实例运行
14. CDN→Google测速不影响用户体验，不应纳入评分（v4.10.20 已 DROP google_latency_ms/google_speed_mbps 两列）
15. 获取IP时不应强制过滤IP段，应先全部获取→测速筛选→反复不好的再淘汰
16. 评分维度必须全部有效，无效维度等于白算且拉低区分度
17. "网页正常但推特私信发不出去"先判平台限流，再判代理闪断
18. CDN 443端口不提供HTTP服务，测速只能用TCP+TLS握手
19. pkill -f "服务名.py" 会自杀，改用 fuser -k 端口/tcp
20. sing-box 字段必须查官方文档确认合法性，禁止凭直觉猜测
21. **v4.10.20 新增**：服务器代码同步必须覆盖根目录文档 + scripts/ + 辅助脚本，不能只 push "经常改的核心 .py"
22. **v4.10.20 新增**：临时调试脚本必须归档到 docs/archive/scripts/，禁止散落在 scripts/ 根目录
23. **v4.10.20 新增**：SQLite 多进程并发场景必须用 WAL 模式（PRAGMA journal_mode = WAL）
24. **v4.10.20 新增**：Reality short_id 严禁使用 abcd1234 等弱预设，必须 `openssl rand -hex 8` 生成

完整避坑记录见 [AI_DEBUG_HISTORY.md](AI_DEBUG_HISTORY.md)

---

## 部署记录

### 新加坡服务器（13.212.37.11）
- 域名：sg.290372913.xyz
- 部署时间：2026-05-04
- 状态：正常运行
- 协议：VLESS-Reality, VLESS-gRPC, Trojan-TCP, VLESS-WS-CDN, VLESS-HTTPUpgrade-CDN, Trojan-WS-CDN, Hysteria2
- vless-grpc 端口: 51263
- trojan-tcp 端口: 14497
- sing-box：1.13.11（CHANGELOG v4.11.0 计划升级 1.15.0 未实际执行）

### 日本服务器（52.195.179.240）
- 域名：jp.290372913.xyz
- 部署时间：2026-05-03
- 状态：正常运行
- 协议：VLESS-Reality, VLESS-gRPC, Trojan-TCP, VLESS-WS-CDN, VLESS-HTTPUpgrade-CDN, Trojan-WS-CDN, Hysteria2
- vless-grpc 端口: 36848
- trojan-tcp 端口: 64688
- sing-box：1.13.11（CHANGELOG v4.11.0 计划升级 1.15.0 未实际执行）

### 香港服务器 (43.249.174.222)
- 域名: hk.290372913.xyz
- 系统: Debian 12
- 协议: VLESS-Reality, VLESS-gRPC, Trojan-TCP, VLESS-WS-CDN, VLESS-HTTPUpgrade-CDN, Trojan-WS-CDN
- TUIC v5: 已启用（ENABLE_TUIC=true）
- 部署时间: 2026-06-04
- vless-grpc 端口: 51794
- trojan-tcp 端口: 65004
- sing-box：1.13.9（CHANGELOG v4.11.0 计划升级 1.15.0 未实际执行）
