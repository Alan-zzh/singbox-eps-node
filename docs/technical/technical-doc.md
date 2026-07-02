# Singbox EPS Node 技术文�?
**版本**: v4.14.0 | **更新**: 2026-06-27

> 版本历史�?CHANGELOG.md 为准。本文档描述当前架构和模块说明�?
---

## 一、项目概�?
全自动CDN优选IP管理 + 多协议代理订阅生成系统。一条命令完成部�?客户端导入订阅即可使用�?
- **代理内核**: sing-box 1.13.13(SG/HK) / 1.13.14(JP)
- **后端**: Python 3 + Flask
- **数据�?*: SQLite(WAL 模式)
- **CDN**: Cloudflare
- **证书**: Let's Encrypt / Cloudflare Origin CA

---

## 二、架�?
### 服务列表
| 服务 | 端口 | 说明 |
|------|------|------|
| singbox | 443, 8443, 2083, 2096, VLESS_GRPC_PORT, TROJAN_TCP_PORT | 代理内核（v4.14.0 精简 6 协议�?|
| singbox-sub | 2087 | HTTPS订阅（走CDN�?|
| singbox-cdn | - | CDN优选IP监控（v4.0 用户反馈驱动版，每小时存活检测） |

### 节点列表（v4.14.0 精简 7�?�?| 节点 | 地址 | 方式 |
|------|------|------|
| {CC}-VLESS-Reality | {IP}:443 | 直连 |
| {CC}-VLESS-gRPC | {IP}:VLESS_GRPC_PORT | 直连（Base64 URI 补充 gRPC 兼容参数�?|
| {CC}-Trojan-TCP | {IP}:TROJAN_TCP_PORT | 直连 |
| {CC}-VLESS-WS-CDN | 优选IP:8443 | CDN |
| {CC}-Trojan-WS-CDN | 优选IP:2083 | CDN |
| {CC}-anyTLS | {IP}:2096 | 直连（v4.14.0 新增，缓�?TLS-in-TLS 指纹�?|

⚠️ v4.14.0 删除：VLESS-HTTPUpgrade-CDN（故障最�?兼容最窄）、TUIC v5（UDP 易被�?QUIC �?QoS�?⚠️ AI-SOCKS5是幕后路由出站，不是用户可见节点。不出现在订阅链接和selector中，AI网站流量自动走SOCKS5，用户无感�?
### 端口分配（v4.14.0 更新�?| 端口 | 用�?| CDN |
|------|------|-----|
| 443 | VLESS-Reality | �?|
| 2083 | Trojan-WS-CDN | �?|
| 2087 | 订阅服务 | �?|
| 8443 | VLESS-WS-CDN | �?|
| 2096 | anyTLS（v4.14.0 新增�?| ❌（直连源站�?|
| VLESS_GRPC_PORT | VLESS-gRPC（随�?0000-65535�?| �?|
| TROJAN_TCP_PORT | Trojan-TCP（随�?0000-65535�?| �?|
| 1080 | SOCKS5本地代理 | �?|
| ~~2053~~ | ~~VLESS-HTTPUpgrade-CDN（v4.14.0 已下线）~~ | - |
| ~~TUIC_PORT~~ | ~~TUIC v5（v4.14.0 已下线）~~ | - |

### 文件结构
```
/root/singbox-eps-node/
├── .env                    # 环境变量（所有配置集中管理）
├── config.json             # singbox配置
├── cert/                   # SSL证书（cert.pem/fullchain.pem + key.pem�?├── data/
�?  ├── singbox.db          # SQLite数据�?�?  └── .port_lock          # 端口锁定文件
├── scripts/
�?  ├── config.py           # 全局配置（唯一真相源）
�?  ├── config_generator.py # sing-box配置生成�?�?  ├── subscription_service.py # HTTPS订阅服务
�?  ├── cert_manager.py     # 证书管理
�?  ├── cdn_monitor.py      # CDN优选IP监控
�?  ├── tg_bot.py           # Telegram机器�?�?  ├── logger.py           # 日志管理
�?  ├── health_check.sh     # 健康检查（�?分钟�?�?  └── diagnose.sh         # 一键诊断脚本（14项检查）
├── logs/
└── backups/
```

---

## 三、核心模�?
### config.py �?配置中心
- 服务器IP自动检测（`_detect_server_ip()`�?- 域名/IP动态判断（`get_sub_domain()`�?- 端口硬编码锁�?+ SHA256校验和防篡改
- .env文件读取，TUIC规避配置，SOCKS5凭据从环境变量读�?- `.env` 解析优先 `python-dotenv`，降级时兼容历史 `KEY=  # 注释` 遗留格式
- COUNTRY_CODE�?env读取，NODE_PREFIX动态生�?
### subscription_service.py �?订阅服务
- Flask应用，监�?087端口（CDN支持端口�?- Base64编码订阅（V2rayN/NekoBox等）
- sing-box JSON完整配置（含路由规则，rule_set格式�?- CDN优选IP自动分配（每个协议独立IP�?- CDN纠错机制：get_cdn_ip_for_protocol()连通性检测，连不上自动回退域名（Bug #57�?- SOCKS5 AI路由规则（可选项，默认关闭，开启时13个AI域名走住宅代理，X/推特/groK排除�?- SOCKS5代理检测：check_single_socks5()用socket替换sock_mod，finally确保关闭
- TUIC v5 端口配置
- 按月流量统计（SQLite持久化，每月14号自动归零）
- /api/traffic JSON接口

### config_generator.py �?服务端配置生�?- 5个入站配�?+ SOCKS5本地代理
- 自动生成密码和UUID
- AI SOCKS5出站 + 路由规则
- 所有路径从config.py的BASE_DIR/CERT_DIR拼接
- 证书缺失时自动调用cert_manager.py生成自签名证�?- DNS已迁移到 sing-box 新格式（`type/server`），并显式写 `route.default_domain_resolver`，不再依�?deprecated 环境变量

### DNS兼容性说明（2026-05-10新增�?- 旧写法：`address: "tls://8.8.8.8"`、`address: "h3://dns.alidns.com/dns-query"`、`address: "rcode://success"`、`address: "fakeip"`
- 新写法：显式拆成 `type`、`server`、`path`、`rcode` 等字�?- 服务�?`config.json` 和订阅服务生成的 sing-box JSON 都必须同步迁�?- `route.default_domain_resolver` 必须显式存在，不能再�?systemd �?`ENABLE_DEPRECATED_LEGACY_DNS_SERVERS` / `ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER` 顶着�?- 结论：当前代码已经按新格式生成，后续同步到服务器后，升级 sing-box 1.14 才不会再因为 DNS 兼容问题翻车

### cdn_monitor.py �?CDN优选IP学习系统（v4.0 用户反馈驱动版）

**核心理念：一切以用户反馈为准，服务器只做存活检�?*

**v4.0 根本改变�?*
| 维度 | v3.x（旧�?| v4.0（新�?|
|------|-----------|-----------|
| 测试方式 | 全量HTTP延迟测试�?50�?�?| TCP存活检测（~100次） |
| 延迟判断 | 服务器主观测延迟 | 不测延迟，以用户反馈为准 |
| IP优先�?| 外部API+本地池公平竞�?| 用户IP优先，外部IP备胎 |
| 速度 | 几分�?| 2秒完�?|

**工作流程�?*
1. 用户投喂IP池（config.py的CDN_PREFERRED_IPS�? 真理来源
2. 外部API补充候选（仅当用户IP不足时）
3. TCP存活检测（443端口�?秒超时）
4. 优先选用户IP，不足再补外部IP
5. 写入数据库（key: vless_ws_cdn_ip/vless_upgrade_cdn_ip/trojan_ws_cdn_ip�?
**评分算法�?* 存活率评�?= alive_count / total_checks * 100

**v4.0 重构原因�?*
- 服务器在新加�?日本测的延迟≠中国用户体�?- 全量HTTP测试浪费资源，IP越多越慢
- 用户投喂的IP才是用户自己测过觉得好的

⚠️ v3.x评分规则（数据源可信度分+排名加分+交叉验证+IP段参考分）已废弃
⚠️ HTTP真实延迟测试已废弃，改为TCP存活检�?自动同步：cdn_monitor每小时更新IP �?subscription_service实时读取 �?用户更新订阅即可

### cert_manager.py �?证书管理
- Cloudflare API源证书（15年有效期�?- 自签证书备用�?65天）
- 自动续签检�?- iptables持久�?
### health_check.sh �?健康检查与自动恢复
- **config.json自愈**（v3.0.1新增）：config.json不存在时自动运行config_generator.py恢复
- **JSON语法校验**（v3.1.3新增）：config.json损坏时自动重新生�?- 端口完整性校验、服务状态检查与自动重启
- 订阅接口可用性检查（从config.py读取SUB_PORT，不再硬编码�?- 防火墙状态检查、证书有效期检查、磁盘空间检�?- Swap检查（v3.1.3新增）、iptables流量计数器检查（v3.1.3新增�?
### 三层自愈机制（v3.0.1新增�?| 层级 | 机制 | 说明 |
|------|------|------|
| �?�?| systemd ExecStartPre | singbox启动前自动检查config.json，缺失则生成 |
| �?�?| health_check.sh | �?分钟检查config.json+服务状态，异常自动恢复 |
| �?�?| StartLimitBurst=5 | singbox连续崩溃�?0秒内最多重�?�?|

### cdn_monitor.py �?CDN优选IP学习系统
- 进程锁（v3.0.1新增）：fcntl.flock防止多实例运行导致内存泄�?- while True循环自带定时，不需要crontab重启
- 测试历史自动清理：cleanup_old_history()保留7天（v3.1.3新增�?
### tg_bot.py �?Telegram管理机器�?- 可用命令�?状�?/续签 /订阅 /重启 /优�?/设置住宅 /删除住宅
- batch_update_env()批量更新.env，避免多次服务重启（v3.1.3新增�?- 异常信息写日志不返回用户，Token不打印（v3.1.3安全加固�?
---

## 四、功能清�?
### 1. HTTPS订阅服务
- Base64: `https://{CF_DOMAIN}:2087/sub/{CC}`
- sing-box JSON: `https://{CF_DOMAIN}:2087/singbox/{CC}`
- 证书: Let's Encrypt（acme.sh自动续期�?- ⚠️ 必须用域名访问，IP访问证书不匹�?
### 2. TUIC v5 协议
- **协议原理**：基�?QUIC（UDP）传输，内置 TLS 1.3（QUIC 强制加密），TCP+UDP 双栈代理
- **配置参数**�?  - `congestion_control: bbr` �?BBR 拥塞控制，不依赖丢包
  - `alpn: h3` �?HTTP/3 ALPN 协商
  - `uuid + password` 认证 �?�?.env 读取，安装时自动生成
  - 随机端口�?0000-65535）�?避免固定端口被识别，支持 .env 手动修改
- **�?Hysteria2 的区�?*�?  - 无端口跳跃：QUIC 自带连接迁移（Connection ID），不需�?TCP 时代的端口跳�?  - �?obfs 混淆：TUIC v5 指纹更低调，不需�?salamander 等额外混�?  - 不复�?443：独立随机端口，不与 VLESS-Reality 共享
  - TCP+UDP 双栈：同时代�?TCP �?UDP 流量（HY2 �?UDP 加速）
- **证书复用**：使�?cert/fullchain.pem（与 CDN 协议共享自签证书�?- **一键回退**：HK �?ISP 阻断 UDP 时，`ENABLE_TUIC=false` 可禁�?
### 3. CDN优选IP（v2.0.0 多源聚合+评分排序�?1. vvhan API（中国实测，含延�?速度/数据中心，每15分钟更新，可信度最高）
2. 090227电信API（中国电信实测，�?62.159段）
3. 001315电信API（中国电信实测，混合段）
4. WeTest DNS（DoH解析，质量不稳定�?5. IPDB API（通用优选，大量104段）
6. 本地实测IP池（兜底�?
#### CDN优选IP评分规则（v2.0.0 - Bug #41教训重构�?
**评分公式：总分 = 数据源可信度�?+ 排名加分 + 交叉验证加分 + IP段参考分**

**数据源可信度权重�?*
| 数据�?| 权重 | 说明 |
|--------|------|------|
| vvhan API | +30 | 中国实测，含延迟/速度/数据中心，每15分钟更新 |
| 090227 API | +25 | 中国电信实测，纯162.159�?|
| 001315 API | +15 | 中国电信实测，混合段（含8.39段） |
| WeTest DNS | +10 | DoH解析，质量不稳定 |
| IPDB API | +5 | 通用优选，大量104�?|
| 本地�?| +0 | 兜底 |

**IP段参考分（软参考，不硬过滤）：**
| IP�?| 分数 | 说明 |
|------|------|------|
| 162.159.x.x | +10 | 用户实测最优段�?0-53ms |
| 108.162.x.x | +10 | 用户实测最优段�?0-51ms |
| 172.64.x.x | +8 | 用户实测优质段，50-53ms |
| 173.245.x.x | +8 | vvhan电信推荐�?0-55ms |
| 198.41.x.x | +8 | vvhan电信推荐�?0-55ms |
| 104.16-21.x.x | -10 | 实测延迟�?66-130ms)，降权但不丢�?|
| 8.39/8.35.x.x | -5 | 实测数据不支持，降权 |

**交叉验证加分�?* 同一IP被N个数据源推荐，额�?(N-1)×15�?
**核心改变（v2.0.0 vs v1.0.85）：**
- v1.0.85：按IP段前缀硬过滤，104段直接丢弃，8.39段直接丢�?- v2.0.0：综合评分排序，104段降权但不丢弃，8.39段降权但不丢�?- 优势：不再一刀切，多源交叉验证的IP质量更可�?
#### CDN数据源详细调研记录（v2.0.0 新增，供后续AI/开发者参考）

> 以下内容记录了v2.0.0重构时对所有CDN优选IP数据源的调研过程�?> 包括每个API的地址、返回格式、实际返回示例、质量评估、可信度评分依据�?> **目的**：让后续接手的AI或开发者能理解"为什么这样评�?，而不是盲目调参�?
##### 数据�?：vvhan API（可信度最高，+30分）

- **API地址**：`https://api.vvhan.com/tool/cf_ip`
- **展示页面**：`https://cf.vvhan.com/`
- **更新频率**：每15分钟
- **返回格式**：JSON
- **返回示例**�?026-04-25实测）：
```json
{
  "success": true,
  "data": {
    "v4": {
      "CT": [
        {"ip": "108.162.196.94", "latency": 50, "speed": "647"},
        {"ip": "108.162.193.55", "latency": 51, "speed": "647"},
        {"ip": "162.159.26.40", "latency": 52, "speed": "647"}
      ],
      "CM": [...],
      "CU": [...]
    },
    "v6": { "CT": [], "CM": [], "CU": [] }
  }
}
```
- **电信实测IP**�?026-04-25 07:00:00）：
  - 108.162.196.94 �?SIN(新加�?
  - 108.162.193.55 �?SIN
  - 162.159.26.40 �?SIN
  - 108.162.192.188 �?SIN
  - 162.159.5.112 �?SIN
- **联通实测IP**�?62.159.11.x �?LAX(洛杉�?
- **移动实测IP**�?04.26.7.x �?SEA(西雅�?
- **为什么可信度最�?*�?  1. 返回JSON格式，包含延�?latency)、速度(speed)、数据中�?colo)信息
  2. 按运营商分类（CT电信/CM移动/CU联通），可精确匹配目标用户�?  3. �?5分钟更新，数据时效性最�?  4. 电信推荐IP全部走SIN(新加�?节点，与用户实测数据一�?  5. 基于 XIU2/CloudflareSpeedTest 工具实测，方法论可靠
- **代码解析方式**：`fetch_from_vvhan_ct()` 解析JSON，提�?`data.v4.CT` 列表

##### 数据�?�?90227电信API（可信度第二�?25分）

- **API地址**：`https://addressesapi.090227.xyz/ct`
- **其他线路**：`/cm`(移动) `/cu`(联�?
- **返回格式**：纯文本，每�?`IP#运营商`
- **返回示例**�?026-04-25实测）：
```
162.159.153.144#CT
162.159.153.156#CT
162.159.153.72#CT
162.159.152.31#CT
162.159.153.170#CT
162.159.153.216#CT
```
- **特点**�?  1. 返回�?62.159.x.x段IP，与用户实测最优段完全一�?  2. IP排序=中国电信实测延迟从低到高
  3. 格式简单，解析方便（`line.split('#')[0]`�?- **为什么排第二**：不含延�?速度等详细信息，无法做更精细的筛�?- **代码解析方式**：`fetch_from_090227_ct()` 按行解析，提�?前的IP

##### 数据�?�?01315电信API（可信度第三�?15分）

- **API地址**：`https://cf.001315.xyz/ct`
- **其他线路**：`/cm`(移动) `/cu`(联�?
- **返回格式**：纯文本，每�?`IP#运营商`
- **返回示例**�?026-04-25实测）：
```
8.39.125.195#电信
173.245.59.30#电信
162.159.33.148#电信
8.39.125.139#电信
173.245.59.55#电信
8.39.125.28#电信
```
- **特点**�?  1. 返回混合段IP�?.39/173.245/162.159
  2. IP排序=中国电信实测延迟从低到高
  3. 8.39段排在前面，但实测数据不支持其为优质�?- **为什么排第三**�?  - 8.39段IP排在前面但未被其他数据源验证
  - 173.245段是优质段，与vvhan/090227交叉验证一�?  - 162.159段也是优质段
  - 综合来看：部分IP可信，但8.39段存疑，所以权重低�?90227
- **v2.0.0改进**：不再硬过滤8.39段，而是通过IP段参考分(-5)降权，如�?.39段IP被其他源交叉验证推荐，仍有机会入�?- **代码解析方式**：`fetch_from_001315_ct()` 按行解析，提�?前的IP

##### 数据�?：WeTest DNS（可信度第四�?10分）

- **DNS地址**：`ct.cloudflare.182682.xyz`（电信优选）
- **其他线路**：`cm.cloudflare.182682.xyz`(移动) `cu.cloudflare.182682.xyz`(联�?
- **展示页面**：`https://www.wetest.vip/page/cloudflare/address.html`
- **返回格式**：DNS A记录，需通过DNS解析获取IP
- **解析方式**：必须用DoH(DNS over HTTPS)从境外服务器解析
  - 正确DoH：`https://dns.alidns.com/resolve?name=ct.cloudflare.182682.xyz&type=A`
  - 错误方式：直接dig @8.8.8.8（返�?04段，Bug #27教训�?- **为什么可信度�?*�?  1. DNS记录本身可能返回104.18.x.x段（即使用中国DNS解析也是104段）
  2. 104段对中国用户延迟130ms+（Bug #29教训�?  3. DNS解析结果不如API排序精确
- **代码解析方式**：`fetch_from_wetest_ct()` 通过DoH解析获取IP列表

##### 数据�?：IPDB API（可信度第五�?5分）

- **API地址**：`https://ipdb.api.030101.xyz/?type=bestcf`
- **返回格式**：纯文本，每行一个IP
- **返回示例**�?026-04-25实测）：
```
104.16.144.115
104.17.145.73
104.17.210.105
172.64.155.57
104.19.38.170
198.41.209.203
```
- **为什么可信度最�?*�?  1. 大量104.16-19段IP，对中国延迟�?  2. 不按运营商分类，返回的是通用"bestcf"
  3. 172.64/198.41段偶有优质IP，但占比极低
- **代码解析方式**：`fetch_from_ipdb_api()` 按行解析纯IP

##### 数据�?：本地实测IP池（兜底�?0分）

- **定义位置**：`config.py` �?`CDN_PREFERRED_IPS` 列表
- **用�?*：所有外部API不可用时的最后兜�?- **更新方法**�?  1. 访问 `https://cf.vvhan.com/` 查看电信推荐IP
  2. 访问 `https://cf-ip.cdtools.click/beijing` 查看北京地区测速结�?  3. 使用 XIU2/CloudflareSpeedTest 工具从中国网络实�?  4. 只选取162.159/172.64/108.162/173.245/198.41段的IP
  5. 按延迟从低到高排�?  6. 同步更新config.py和cdn_monitor.py的ImportError降级�?
##### 其他已知数据源（未使用，备查�?
| 数据�?| 地址 | 说明 | 未使用原�?|
|--------|------|------|-----------|
| stock.hostmonit.com | `https://stock.hostmonit.com/CloudFlareYes` | 返回HTML表格含延�?丢包/速度 | 解析复杂，数据量�?|
| cf-ip.cdtools.click | `https://cf-ip.cdtools.click/beijing` | 按城市测速，含延�?丢包/速度 | 无API接口，仅HTML展示 |
| monitor.gacjie.cn | `https://monitor.gacjie.cn/api/client/get_ip_address` | JSON格式含延�?| 响应不稳�?|
| ip.164746.xyz | `https://ip.164746.xyz` | CF优选IP | 返回HTML无结构化数据 |
| ip.haogege.xyz | `https://ip.haogege.xyz` | CF优选IP | 返回HTML无结构化数据 |
| api.uouin.com | `https://api.uouin.com/cloudflare.html` | CF优选IP | 返回HTML无结构化数据 |

##### 评分逻辑推导过程

**问题**：从日本服务器无法直接测出对中国用户的延迟和带宽（因为距离CF节点太近，TCPing都是1-2ms），所以必须依赖从中国实测的第三方API�?
**旧方案（v1.0.85）的问题**�?- 按IP段前缀硬过滤（`is_hunan_ct_optimal()`），162.159/172.64=优质�?04�?丢弃
- 001315 API返回�?.39段被直接丢弃，但8.39段可能是中国电信实测排序�?- 单一数据源依赖（090227优先），API挂了就降级到不可靠源
- 没有交叉验证，无法区�?多个源都推荐的IP"�?只有一个源推荐的IP"

**新方案（v2.0.0）的推导**�?1. 既然无法从服务器端实测，那就信任从中国实测的API排序
2. 不同API的可信度不同：vvhan含延迟数�?> 090227�?62.159�?> 001315�?.39�?3. 如果一个IP被多个API同时推荐，说明它的质量确实好（交叉验证）
4. IP段前缀作为参考因素但不硬过滤�?04段大概率�?-10�?，但不排除个别好IP
5. 最终按综合评分排序，选TOP N

**评分公式各参数的取值依�?*�?- 数据源权�?30/25/15/10/5/0)：拉开差距，确保高可信源优�?- 排名加分(20/18/16...)：API排序本身就是实测结果，排名靠前的应该加分
- 交叉验证(+15/�?：被2个源推荐+15�?个源+30，确保交叉验证有足够权重
- IP段参考分(+10/+8/-10/-5)：基于历史实测数据，但不硬过�?
**模拟验证结果**�?026-04-25）：
```
场景1：各源返回不同IP
  #1: 108.162.196.94 (评分=60, 来源=vvhan)
  #2: 108.162.193.55 (评分=58, 来源=vvhan)
  #3: 162.159.26.40  (评分=56, 来源=vvhan)
  #4: 162.159.153.144 (评分=55, 来源=090227)
  #5: 108.162.192.188 (评分=54, 来源=vvhan)

场景2：交叉验证（162.159.26.40�?个源推荐�?  162.159.26.40 | 总分=170 (�?70 排名=60 交叉=30 �?10) | vvhan+090227+001315 x3
  162.159.5.112 | 总分=116 (�?55 排名=36 交叉=15 �?10) | vvhan+090227 x2
  162.159.153.144 | 总分=51 (�?25 排名=16 交叉=0 �?10) | 090227
```

### 4. SOCKS5 AI路由（v4.1.0 可选项�?- **触发条件**: AI_SOCKS5_ROUTING=on（默认off�?- **AI网站走SOCKS5**: openai/anthropic/gemini/perplexity/google�?- **X/推特/groK排除**: 走ePS-Auto正常代理
- **幕后路由，用户无需手动选择**
- **配置方式**:
  - install.sh安装时交互配�?  - tg_bot.py /AI路由 一键开�?  - 直接编辑.env文件 AI_SOCKS5_ROUTING=on/off
- **关闭�?*: 所有流量走正常协议（VLESS/Trojan/TUIC），不经过SOCKS5
- **生效时机**: 修改配置后立即重启服务生�?
### 5. 按月流量统计（v3.1.1重构�?- **数据来源**: iptables内核级流量计数器（sing-box各入站端口）
- **统计维度**: 所有sing-box入站端口(443/8443/2053/2083)的TCP流量总和
- **实现方式**: 
  1. `setup_iptables_traffic_counters()` - 启动时在INPUT链添加端口统计规则（幂等�?  2. `get_iptables_traffic_bytes()` - 解析`iptables -L INPUT -v -n -x`提取bytes计数�?  3. `check_and_reset_month()` - 首次升级初始化iptables_baseline，每�?4号更新基准�?  4. `get_traffic_stats()` - 返回iptables当前�?基准�?当月流量
- 每月14号自动归�?- API: `/api/traffic`（返回JSON�?- 首页蓝色流量统计区域
- **优势**: 内核级计数器，持久化、重启不丢失，与机场面板相同做法
- **Clash API不可用原�?*:
  - sing-box 1.10.0编译标签只有with_clash_api，没有with_v2ray_api
  - Clash API /proxies端点不返回download/upload字段
  - /connections�?traffic是SSE流式端点，不适合简单查�?  - sing-box重启后内存计数器归零，无法持久化
- **subscription-userinfo响应�?*�?  - /sub�?singbox路由的HTTP响应头包含`subscription-userinfo`
  - 格式：`upload=0; download={bytes_used}; total=-1; expire=0`
  - 客户端（v2rayN/Clash/Shadowrocket等）通过此头显示流量信息
  - upload=0：上传流量不统计
  - download={bytes_used}：当月已用下载流量（字节�?  - total=-1：总流量不�?  - expire=0：永不过�?
### 6. SSL证书
- 优先�? fullchain.pem > cert.pem
- 自动续签: acme.sh + cron（每�?号凌�?点）
- 所有引用点统一路径

### 7. BBR+FQ+CAKE网络加�?- BBR: Google拥塞控制，不依赖丢包
- FQ: 公平队列，BBR的pacing依赖
- CAKE: 集成FQ+PIE，防缓冲区膨胀，抗丢包
- 降级: 内核不支持CAKE时自动降级FQ-PIE（tc qdisc replace实际应用到网卡）
- CAKE模块主动安装: modprobe失败时自动安装linux-modules-extra
- 持久�? systemd服务（cake-qdisc@ / fq-pie-qdisc@�?- 即时生效，无需重启

### 8. 安装脚本子命�?- `bash install.sh` �?全新安装
- `bash install.sh reinstall` �?重装操作系统（需root密码�?- `bash install.sh reset` �?重装singbox应用（保留配置）
- `bash install.sh optimize` �?一键优化系�?
### 9. sing-box rule_set�?.12+格式�?- geoip/geosite已移除，改用rule_set远程.srs规则�?- 客户�? geosite-cn.srs / geoip-cn.srs / geosite-geolocation-!cn.srs
- 服务�? 不需要geoip/geosite（catch-all处理direct�?
---

## 五�?env 配置

### 必填
| 变量 | 说明 |
|------|------|
| SERVER_IP | 服务器IP（留空自动检测） |
| CF_DOMAIN | Cloudflare域名 |

### 协议密码（安装时自动生成�?| 变量 | 说明 |
|------|------|
| VLESS_UUID | VLESS Reality UUID |
| VLESS_WS_UUID | VLESS WS/HTTPUpgrade UUID |
| TROJAN_PASSWORD | Trojan-WS密码 |
| HYSTERIA2_PASSWORD | Hysteria2密码（已废弃，保留兼容） |
| TUIC_PASSWORD | TUIC v5密码 |
| REALITY_PRIVATE_KEY | Reality私钥 |
| REALITY_PUBLIC_KEY | Reality公钥 |

### 可�?| 变量 | 说明 |
|------|------|
| CF_API_TOKEN | Cloudflare API Token（证书申请） |
| COUNTRY_CODE | 国家代码（自动检测） |
| SUB_TOKEN | 订阅Token |
| AI_SOCKS5_SERVER | AI SOCKS5服务�?|
| AI_SOCKS5_PORT | AI SOCKS5端口 |
| AI_SOCKS5_USER | AI SOCKS5用户�?|
| AI_SOCKS5_PASS | AI SOCKS5密码 |
| TG_BOT_TOKEN | Telegram Bot Token |
| TG_ADMIN_CHAT_ID | 管理员Chat ID |

### `.env` 书写规则
- 注释必须单独成行，禁止继续写 `KEY=�? # 注释`
- 当前代码已兼容历史遗留的行内注释格式，但这只是兜底，不是推荐写法

---

## 六、编码铁律（避坑指南�?
### 规则1：HTTPS订阅必须用域名访问，禁止用IP
**教训**: v1.0.43用IP访问HTTPS订阅，V2rayN验证SSL证书时发现证书颁发给域名，与IP不匹配，拒绝连接（SEC_E_WRONG_PRINCIPAL�?**做法**: 订阅链接必须用域名格�?`https://{CF_DOMAIN}:{SUB_PORT}/sub/{CC}`

### 规则2：订阅端口必须在Cloudflare CDN支持列表
**教训**: v1.0.43�?443端口，CDN不代理，域名访问时CDN直接丢弃流量
**CDN支持HTTPS端口**: 443, 2053, 2083, 2087, 2096, 8443

### 规则3：TUIC v5 使用随机端口，不需要端口跳�?**教训**: Hysteria2 使用 iptables 200�?DNAT 规则做端口跳跃，�?TCP 时代的产物。QUIC 协议自带连接迁移（Connection ID），端口被封时自动迁移到新端口，不需�?DNAT
**做法**: TUIC v5 使用随机端口�?0000-65535），只需 1 �?TCP + 1 �?UDP iptables 规则

### 规则4：CDN IP获取必须用指定DNS
**教训**: v1.0.36-37用日本服务器DNS解析，返回对中国延迟高的IP�?00ms+�?**做法**: 使用222.246.129.80 / 59.51.78.210（湖南电信DNS），或阿里DoH(dns.alidns.com)
**Bug #29补充**: WeTest.vip即使用中国DNS解析也返�?04.x.x.x段（130ms+），必须过滤后丢弃，不能"全部保留"
**Bug #29补充**: 境外服务器必须用DoH方式解析，直接dig中国DNS会超�?
### 规则5：测试必须模拟真实客户端环境
**教训**: v1.0.43用curl -k测试通过，但V2rayN不用-k，验证证书失�?**做法**: 测试HTTPS服务禁止-k/--insecure

### 规则6：禁止硬编码IP/域名/凭据/路径
**教训**: v1.0.45前大量硬编码，新VPS部署必须手动改代码，极易遗漏
**做法**: 所有IP/域名�?env读，路径从config.py拼，凭据从环境变量读

### 规则7：修改配置必须全局搜索所有引用文�?**教训**: v1.0.50发现13个隐藏问题，根因是改subscription_service.py时没同步改config_generator.py/tg_bot.py/README.md
**做法**: 修改�?`grep -r "关键�? scripts/ *.md`，统一引用config.py作为唯一真相�?
### 规则8：服务重启必须覆盖所有相关服�?**教训**: v1.0.52设置住宅后只重启singbox+singbox-sub，漏了singbox-cdn
**做法**: 重启必须 singbox + singbox-sub + singbox-cdn

### 规则9：AI-SOCKS5是幕后路由出站，不是用户可见节点
**教训**: v1.0.48把AI-SOCKS5当成"节点"加入Base64订阅和selector，用户手动选择后无法正常使�?**做法**: 禁止将幕后路由出站加入订阅链接、selector、首页节点列�?
### 规则10：改代码必须同步更新文档
**教训**: 多次出现"代码改了文档没改"，导致下一个AI基于过时文档犯错
**做法**: 改代码后必须同步更新TECHNICAL_DOC.md，版本号+1

### 规则11：防火墙重置必须在端口跳跃之�?**教训**: v1.0.52中iptables -F清空了刚设置的端口跳跃规�?**做法**: 安装脚本执行顺序：端口跳�?�?防火�?�?服务启动

### 规则12：降级方案必须实际应用到网卡
**教训**: v1.0.75前CAKE降级只设sysctl参数，未通过tc qdisc replace应用到网卡，降级也不生效
**做法**: 降级必须 `tc qdisc replace dev $MAIN_IF root fq_pie`，不能只设sysctl

### 规则13：订阅链接不加token认证
**做法**: 保持原有规则直接访问

### 规则14：数据库连接必须在finally中关�?**教训**: v1.0.54前数据库连接泄漏
**做法**: try/finally确保conn.close()

### 规则15：异常信息禁止返回给用户
**教训**: cdn_api()�?00错误返回str(e)，可能泄露内部路�?SQL语句
**做法**: logger.error记录详细日志，返回通用'Internal server error'

### 规则16：禁止裸except
**做法**: 必须指定Exception，否则会吞掉KeyboardInterrupt/SystemExit

### 规则17：ImportError降级必须定义所有必需变量
**教训**: config.py导入失败时except块只定义了get_logger，后续代码引用SERVER_IP等变量时NameError导致服务无法启动
**做法**: except块中定义所有必需变量的降级�?
### 规则18：小内存VPS必须配Swap
**教训**: 414MB内存无Swap，OOM killer杀掉singbox进程导致掉线（Bug #39�?**做法**: <1GB内存的VPS必须创建2GB Swap，禁用fwupd/snapd等不必要的服�?
### 规则19：日志必须配logrotate
**教训**: singbox日志12MB+且持续增长，无轮转机制（运维#1�?**做法**: /etc/logrotate.d/singbox 配置 daily + rotate 7 + maxsize 50M

### 规则20：免费版 CF 禁止主动创建 DDoS L7 override（v4.12.12�?**教训**: v4.12.12 CDN 全部 403，最初以为是 DDoS L7 拦截，创建了 ddos_l7 zone override（sensitivity_level=eoff）。短暂恢�?200 后又全部 403，且 override、IP 白名单、managed_challenge 都无法解除。实测发�?*主动创建 DDoS L7 override 反而触�?CF 动态保护机�?*，把整个 zone 标记�?被攻�?�?**做法**:
- **不要主动创建 DDoS L7 override**：CF 默认 DDoS L7 配置不会拦截代理入口，v4.12.7 �?skip 规则（WAF/SBFM/Rate Limit）已经足�?- `scripts/cloudflare_proxy_rules.py ensure_ddos_l7_override()` 只查询不创建
- CDN 全部 403 诊断顺序：① 源站直连确认服务正常 �?�?检查是否有 DDoS L7 override（有则删除）�?�?检�?skip 规则 �?�?检�?zone settings �?�?GraphQL �?source
- "短暂有效然后失效"�?CF 动态保护的典型特征，应反向操作（删除而非添加�?- CF DDoS L7 动态签名优先级最高，一旦激�?override/IP 白名�?managed_challenge 都无法解除，只能删除 override 等待 CF 重新评估

---

## 七、Bug修复历史

| # | 版本 | 问题 | 根因 | 修复 |
|---|------|------|------|------|
| 1 | v1.0.39 | Trojan-WS链接缺少insecure=1 | 缺少参数 | 添加insecure=1和allowInsecure=1 |
| 2 | v1.0.37 | CDN优选IP对中国延迟高 | 日本DNS返回不友好IP | 恢复固定优选IP�?|
| 3 | v1.0.41 | Trojan-WS协议不�?| 缺SSL配置+path编码不一�?| 添加SSL+统一URL编码 |
| 4 | v1.0.42 | 订阅端口9443不�?| 默认端口/防火�?CDN三重bug | 端口6969�?443+防火墙放�?|
| 5 | v1.0.44 | V2rayN无法更新订阅 | IP访问HTTPS证书不匹�?| 9443�?087走CDN+域名访问 |
| 6 | v1.0.45 | 新VPS部署困难 | 大量硬编�?| 全面消除硬编�?config.py统一 |
| 7 | v1.0.45 | CDN优选IP过期 | 固定IP�?随机ping | 改指定DNS解析+4级降�?|
| 8 | v1.0.45 | HY2端口跳跃目标错误 | DNAT�?433但HY2监听443 | 目标改为443 |
| 9 | v1.0.49 | AI-SOCKS5暴露为用户节�?| 当成普通节点加入订�?| 移除订阅链接和selector |
| 10 | v1.0.50 | 跨文件配置不一�?| 修改时未全局搜索 | 统一引用config.py |
| 11 | v1.0.50 | HY2端口范围错误+缺TCP | iptables 22000 vs config 21000 | 统一21000-21200+补TCP |
| 12 | v1.0.52 | 证书文件名不一�?| cert.crt vs cert.pem | 统一cert.pem+fullchain.pem |
| 13 | v1.0.52 | 防火墙清除端口跳跃规�?| iptables -F在规则之�?| 调整执行顺序 |
| 14 | v1.0.52 | TG机器人CDN更新死循�?| cdn_monitor.py是无限循�?| 改为import单次执行 |
| 15 | v1.0.52 | 设置住宅后不重启singbox-cdn | 漏了singbox-cdn | 添加systemctl restart |
| 16 | v1.0.52 | HY2端口范围硬编码覆�?| subscription_service.py独立定义 | 删除，用config.py导入 |
| 17 | v1.0.71 | CAKE状态显示矛�?| print_summary硬编码已启用 | 改为tc qdisc实际检�?|
| 18 | v1.0.72 | reinstall声称不需密码 | 混淆应用密码和root密码 | 改为需输入root密码 |
| 19 | v1.0.66 | set -e导致CAKE失败脚本退�?| tc qdisc返回非零�?| 改为cmd && OK || true |
| 20 | v1.0.74 | geoip/geosite�?.12+移除 | sing-box FATAL退�?| 改用rule_set格式 |
| 21 | v1.0.74 | CAKE降级FQ不如FQ-PIE | 选了最基础降级方案 | fq→fq_pie |
| 22 | v1.0.75 | CAKE降级仅设sysctl未应�?| 未tc qdisc replace到网�?| 新增setup_fq_pie_qdisc()+主动安装模块 |
| 23 | v1.0.76 | DNS代理查询延迟飙升 | dns_proxy走ePS-Auto | detour改为direct |
| 24 | v1.0.77 | CDN优选IP不自动更�?| 本地池永远优�?| 外部API优先于本地池 |
| 25 | v1.0.78 | X/推特/groK走SOCKS5 | AI规则在排除规则之�?| 排除规则移到AI规则之前 |
| 26 | v1.0.78 | SOCKS5无故障转�?| selector无fallback | 加direct作为第二选项 |
| 28 | v1.0.82 | AI规则含google.com延迟�?| v2rayN测速走SOCKS5 | 移除通用google域名 |
| 29 | v1.0.82 | CDN返回104段高延迟 | WeTest返回104�?| 001315优先+104段严格过�?|
| 30 | v1.0.82 | config_generator与sub不同�?| 改A忘B | 两个文件必须同步更新 |
| 31 | v1.0.82 | CDN优选IP更新服务卡住 | time.sleep卡住 | crontab每小时重启singbox-cdn |
| 32 | v1.0.83 | config_generator缺DNS和final | 从未添加 | 添加DNS+final:direct |
| 33 | v1.0.83 | 旧面板残留进程和目录 | 只stop/disable | 删服务文�?目录+杀进程 |
| 34 | v1.0.84 | CDN重启crontab未写入install.sh | Bug #31修复只在服务�?| install.sh加crontab兜底 |
| 35 | v1.0.85 | CDN本地池混�?04.x.x.x高延迟IP | 本地池未过滤104�?| 移除104段，替换�?62.159/172.64�?|
| 36 | v1.0.85 | cert_manager续签后漏重启singbox-cdn | restart_singbox()漏服�?| 加singbox-cdn重启 |
| 37 | v1.0.85 | health_check漏检UDP端口(HY2) | 只检查TCP端口 | 增加UDP 443检�?|
| 38 | v1.0.85 | cdn_monitor数据库连接泄�?| conn.close()不在finally | 改try/finally |
| 39 | v1.0.85 | 414MB内存无Swap，OOM杀进程 | 无Swap+fwupd�?44MB | 创建2GB Swap+禁用fwupd |
| 40 | v1.0.85 | HUNAN_CT_OPTIMAL_PREFIXES含未验证�?| 8.39/8.35实测不支�?| 移除8.39/8.35�?01315也加过滤 |

---

## 八、版本历�?
| 版本 | 日期 | 更新 |
|------|------|------|
| v1.0.34 | 04-20 | HTTPS订阅+Cloudflare证书+端口9443 |
| v1.0.38 | 04-20 | sing-box JSON配置+AI流量路由 |
| v1.0.42 | 04-21 | 订阅端口9443不通修�?|
| v1.0.44 | 04-21 | V2rayN订阅失败�?087走CDN+域名访问 |
| v1.0.45 | 04-21 | 全面消除硬编�?DNS优选CDN |
| v1.0.47 | 04-21 | HY2端口跳跃无感切换 |
| v1.0.49 | 04-21 | 修复AI-SOCKS5暴露为用户节�?|
| v1.0.50 | 04-21 | 全面排查13个隐藏坑+跨文件一致�?|
| v1.0.52 | 04-21 | 证书文件名统一+自动续签cron+防火墙顺�?|
| v1.0.54 | 04-21 | subscription_service.py安全加固 |
| v1.0.60 | 04-22 | 按月流量统计 |
| v1.0.65 | 04-22 | BBR+FQ+CAKE三合一加�?|
| v1.0.66 | 04-22 | 修复set -e导致CAKE失败脚本退�?|
| v1.0.72 | 04-22 | reinstall改为操作系统重装+root密码确认 |
| v1.0.74 | 04-22 | geoip/geosite改rule_set+CAKE降级改FQ-PIE |
| v1.0.75 | 04-22 | CAKE模块主动安装+FQ-PIE实际应用到网�?精确诊断 |
| v1.0.84 | 04-24 | CDN每小时crontab重启兜底+旧面板清�?版本号统一 |
| v1.0.85 | 04-25 | 修复CDN本地�?04�?cert漏重�?UDP端口检�?DB连接泄漏+OOM/Swap+8.39/8.35�?|
| v2.0.0 | 04-25 | CDN优选IP重构：多源聚�?综合评分排序，新增vvhan API，不再硬过滤IP段，订阅添加subscription-userinfo�?|
| v3.0.0 | 04-25 | CDN学习系统：IP性能数据�?综合评分+自动淘汰+用户投喂 |
| v3.0.1 | 04-26 | 三层自愈机制+进程锁防泄漏+VPS内存优化(244MB�?81MB)+禁用无用服务 |
| v3.1.2 | 05-01 | CDN纠错机制+HTTP真实延迟测试+config_generator路由规则补全 |
| v3.1.3 | 05-01 | 全面问题修复：淘汰IP过滤/socket泄漏/DB连接/历史清理/tg_bot安全加固/health_check增强/diagnose 18�?|
| v4.0.0 | 05-04 | CDN监控重构为用户反馈驱动版：只测存活、用户IP优先、外部API仅补充、key名称对齐 |

---

## 九、使用说�?
### 安装脚本子命�?| 命令 | 功能 |
|------|------|
| `bash install.sh` | 全新安装（自动优化系�?交互式配置） |
| `bash install.sh reinstall` | 重装操作系统（需root密码，装完自动重启） |
| `bash install.sh reset` | 重装singbox应用（保留配置和数据，客户端无需重配�?|
| `bash install.sh optimize` | 一键优化系统（BBR+FQ+CAKE三合一，即时生效） |

### 服务管理
```bash
systemctl restart singbox singbox-sub singbox-cdn  # 重启所有服�?systemctl status singbox singbox-sub singbox-cdn   # 查看状�?journalctl -u singbox-sub -f                       # 查看日志
```

### 证书管理
```bash
python3 /root/singbox-eps-node/scripts/cert_manager.py --cf-cert  # Cloudflare API申请15年证�?python3 /root/singbox-eps-node/scripts/cert_manager.py --renew    # 手动续签
```

### CDN优选IP手动更新
```bash
python3 /root/singbox-eps-node/scripts/cdn_monitor.py
```

### 健康检�?```bash
bash /root/singbox-eps-node/scripts/health_check.sh  # 手动运行
```
�?分钟自动运行，检查端�?服务/订阅/防火�?证书/磁盘�?
### 流量统计
- 首页: `https://{域名}:2087/`
- API: `https://{域名}:2087/api/traffic`
- 重置: 每月14号自动归�?
### Telegram机器�?�?env中配�?`TG_BOT_TOKEN` �?`TG_ADMIN_CHAT_ID`，可用命令：/状�?/续签 /订阅 /重启 /优�?/设置住宅 /删除住宅

### 卸载
```bash
systemctl stop singbox singbox-sub singbox-cdn
systemctl disable singbox singbox-sub singbox-cdn
rm /etc/systemd/system/singbox*.service /etc/systemd/system/cake-qdisc*.service /etc/systemd/system/fq-pie-qdisc*.service
systemctl daemon-reload
rm -rf /root/singbox-eps-node
netfilter-persistent save
```


---


# Clash 订阅生成铁律

> �?AGENTS.md 迁移而来,AGENTS.md 只保留指针。修�?`scripts/subscription_service.py` �?Clash 相关生成逻辑时必须遵守�?
---

## 1. url-test 策略组三件套与测速方�?
修改 Clash url-test 生成�?必须使用:

- `lazy: false` �?后台持续测�?严禁设为 `true` 导致锁死坏节�?
- `tolerance: 150` �?电信网络波动容忍�?禁止低于 100)
- `interval: 60` �?60 秒测速一�?严禁设为 600s 导致卡顿 10 分钟)
- `url: http://cp.cloudflare.com/generate_204` �?HTTP 协议避免 TLS 握手损�?- `timeout: 5000` �?测速超�?5 �?
违反后果:Clash 自动切换过于迟钝导致发消息卡�?或过于频繁导致连接抖�?Bug #88)�?
---

## 2. 规则 MATCH 必须指向 select �?节点选择)

- MATCH 规则必须指向 `节点选择`(select �?,绝对不能直接指向 `自动选择`(url-test �?
- `节点选择` 的首�?proxy 必须�?`自动选择`,用户可在 UI 自由切换(Bug #89)

---

## 3. 高风险参数禁止恢�?
以下参数在丢包环境下会放大问�?禁止恢复到自动选择�?

- `keep-alive-interval` �?丢包隧道上适得其反
- `tcp-concurrent` �?频繁触发连接 RST
- `unified-delay` �?干扰判断

---

## 4. 客户端协议兼容矩�?
用户要求默认保留完整 7 节点。VLESS-HTTPUpgrade(`type=httpupgrade`)�?TUIC v5(`tuic://`)在部�?Xray-core 客户端不稳定时，只能通过 `?client=standard` 手动兜底，不能默认删节点�?
| 客户�?| 节点�?| 说明 |
|--------|--------|------|
| Clash / sing-box / NekoBox | 7 | 完整协议�?|
| v2rayN / v2rayNG / Shadowrocket / Quantumult X | 7 | 默认完整订阅，URI 参数做兼容优�?|
| `?client=standard` | 5 | 手动兜底，剔�?HTTPUpgrade + TUIC |

- `?client=full` 强制 7 节点
- `?client=standard` 强制 5 节点
- **禁止未经用户确认默认删节�?*
- Shadowrocket 节点可用性判断优先看 CONNECT/HTTP 测速和真实连接；ICMP 仅作裸线路参考�?
---

## 5. 订阅流量统计

- iptables 必须 INPUT + OUTPUT 双向计数:INPUT �?`--dport`,OUTPUT �?`--sport`
- UDP 端口(TUIC v5 QUIC 协议)独立建规�?- `get_iptables_traffic_bytes()` 必须 INPUT+OUTPUT 求和,否则下载流量被低�?50%
- 每月 14 号由订阅服务更新数据�?baseline,不清�?iptables 内核计数�?
---

## 6. v2rayN 流量显示限制

v2rayN 不解�?`subscription-userinfo` header,订阅更新只显�?成功: N 个节�?,永远不显示流量�?
- 新增 `/info` 端点(v2rayN 浏览器能�?
- Base64 头部插入流量注释�?部分客户端可�?作为补充
- **禁止期望 v2rayN 通过 subscription 显示流量**

---

## 7. HTTP header 不能含非 ASCII 字符

Flask `Response.headers` 只能设置 latin-1 编码的值�?
- `Content-Disposition: attachment; filename=香港订阅.txt` 会触�?UnicodeEncodeError 导致 500
- 修复:RFC 5987 `filename*=UTF-8''URL编码`,�?profile-title 改为�?ASCII
- **任何通过 header 传递中文字符必�?URL-encode**

