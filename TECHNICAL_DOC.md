# Singbox EPS Node 技术文档

**版本**: v3.0.1 | **更新**: 2026-04-26

---

## 一、项目概述

全自动CDN优选IP管理 + 多协议代理订阅生成系统。一条命令完成部署，客户端导入订阅即可使用。

- **代理内核**: sing-box 1.10.0
- **后端**: Python 3 + Flask
- **数据库**: SQLite
- **CDN**: Cloudflare
- **证书**: Let's Encrypt / Cloudflare Origin CA

---

## 二、架构

### 服务列表
| 服务 | 端口 | 说明 |
|------|------|------|
| singbox | 443, 8443, 2053, 2083 | 代理内核 |
| singbox-sub | 2087 | HTTPS订阅（走CDN） |
| singbox-cdn | - | CDN优选IP监控（每小时，进程锁防重复启动） |

### 节点列表
| 节点 | 地址 | 方式 |
|------|------|------|
| {CC}-VLESS-Reality | {IP}:443 | 直连 |
| {CC}-VLESS-WS-CDN | 优选IP:8443 | CDN |
| {CC}-VLESS-HTTPUpgrade-CDN | 优选IP:2053 | CDN |
| {CC}-Trojan-WS-CDN | 优选IP:2083 | CDN |
| {CC}-Hysteria2 | {IP}:443 | 直连，端口跳跃21000-21200 |

⚠️ AI-SOCKS5是幕后路由出站，不是用户可见节点。不出现在订阅链接和selector中，AI网站流量自动走SOCKS5，用户无感。

### 端口分配
| 端口 | 用途 | CDN |
|------|------|-----|
| 443 | VLESS-Reality + Hysteria2 | ✅ |
| 2053 | VLESS-HTTPUpgrade-CDN | ✅ |
| 2083 | Trojan-WS-CDN | ✅ |
| 2087 | 订阅服务 | ✅ |
| 8443 | VLESS-WS-CDN | ✅ |
| 1080 | SOCKS5本地代理 | ❌ |
| 21000-21200 | HY2端口跳跃→443 | ❌ |

### 文件结构
```
/root/singbox-eps-node/
├── .env                    # 环境变量（所有配置集中管理）
├── config.json             # singbox配置
├── cert/                   # SSL证书（cert.pem/fullchain.pem + key.pem）
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
│   ├── health_check.sh     # 健康检查（每5分钟）
│   └── diagnose.sh         # 一键诊断脚本（14项检查）
├── logs/
└── backups/
```

---

## 三、核心模块

### config.py — 配置中心
- 服务器IP自动检测（`_detect_server_ip()`）
- 域名/IP动态判断（`get_sub_domain()`）
- 端口硬编码锁定 + SHA256校验和防篡改
- .env文件读取，HY2规避配置，SOCKS5凭据从环境变量读取
- COUNTRY_CODE从.env读取，NODE_PREFIX动态生成

### subscription_service.py — 订阅服务
- Flask应用，监听2087端口（CDN支持端口）
- Base64编码订阅（V2rayN/NekoBox等）
- sing-box JSON完整配置（含路由规则，rule_set格式）
- CDN优选IP自动分配（每个协议独立IP）
- SOCKS5 AI路由规则（写死的域名列表，X/推特/groK排除）
- HY2端口跳跃 hop_ports 字段
- 按月流量统计（SQLite持久化，每月14号自动归零）
- /api/traffic JSON接口

### config_generator.py — 服务端配置生成
- 5个入站配置 + SOCKS5本地代理
- 自动生成密码和UUID
- AI SOCKS5出站 + 路由规则
- 所有路径从config.py的BASE_DIR/CERT_DIR拼接
- 证书缺失时自动调用cert_manager.py生成自签名证书

### cdn_monitor.py — CDN监控（v2.0.0 多源聚合+评分排序）
1. vvhan API（中国实测，含延迟/速度/数据中心，每15分钟更新，可信度最高）
2. 090227电信API（中国电信实测，纯162.159段）
3. 001315电信API（中国电信实测，混合段）
4. WeTest.vip电信优选DNS（DoH解析，质量不稳定）
5. IPDB API bestcf（通用优选，大量104段）
6. 本地实测IP池（兜底）

评分公式：总分 = 数据源可信度分 + 排名加分 + 交叉验证加分 + IP段参考分
- 不再按IP段前缀硬过滤，改为综合评分排序
- 同一IP被多个数据源推荐则大幅加分（交叉验证，每个额外源+15分）
- 104段不直接丢弃，但降低权重（-10分）
- 162.159/108.162段加分（+10分），172.64/173.245/198.41段加分（+8分）

⚠️ Bug #29教训：WeTest.vip返回104.x.x.x段对中国延迟130ms+，评分系统自动降权
⚠️ Bug #31教训：~~time.sleep(3600)会卡住，crontab每小时0分重启singbox-cdn兜底保障~~ 已废弃：cdn_monitor.py加进程锁后不再需要crontab重启（Bug #51）
⚠️ Bug #41教训：硬过滤IP段导致优质IP被丢弃，必须用评分制替代
自动同步：cdn_monitor每小时更新IP写入数据库 → subscription_service每次订阅请求实时读取 → 用户更新订阅即可获取最新IP

### cert_manager.py — 证书管理+端口跳跃
- Cloudflare API源证书（15年有效期）
- 自签证书备用（365天）
- 自动续签检查
- Hysteria2端口跳跃iptables规则（UDP+TCP双协议）
- iptables持久化

### health_check.sh — 健康检查与自动恢复
- **config.json自愈**（v3.0.1新增）：config.json不存在时自动运行config_generator.py恢复
- 端口完整性校验、服务状态检查与自动重启
- 订阅接口可用性检查、防火墙状态检查
- 证书有效期检查、磁盘空间检查

### 三层自愈机制（v3.0.1新增）
| 层级 | 机制 | 说明 |
|------|------|------|
| 第1层 | systemd ExecStartPre | singbox启动前自动检查config.json，缺失则生成 |
| 第2层 | health_check.sh | 每5分钟检查config.json+服务状态，异常自动恢复 |
| 第3层 | StartLimitBurst=5 | singbox连续崩溃时60秒内最多重启5次 |

### cdn_monitor.py — CDN优选IP学习系统
- 进程锁（v3.0.1新增）：fcntl.flock防止多实例运行导致内存泄漏
- while True循环自带定时，不需要crontab重启

### tg_bot.py — Telegram管理机器人
- 可用命令：/状态 /续签 /订阅 /重启 /优选 /设置住宅 /删除住宅

---

## 四、功能清单

### 1. HTTPS订阅服务
- Base64: `https://{CF_DOMAIN}:2087/sub/{CC}`
- sing-box JSON: `https://{CF_DOMAIN}:2087/singbox/{CC}`
- 证书: Let's Encrypt（acme.sh自动续期）
- ⚠️ 必须用域名访问，IP访问证书不匹配

### 2. Hysteria2端口跳跃
- iptables DNAT: 21000-21200 → 443（UDP+TCP双协议）
- 客户端: `hop_ports: "21000-21200"`
- 规避: obfs=salamander + 端口跳跃 + alpn=h3
- 无感切换：某端口被封自动跳其他端口，不断线

### 3. CDN优选IP（v2.0.0 多源聚合+评分排序）
1. vvhan API（中国实测，含延迟/速度/数据中心，每15分钟更新，可信度最高）
2. 090227电信API（中国电信实测，纯162.159段）
3. 001315电信API（中国电信实测，混合段）
4. WeTest DNS（DoH解析，质量不稳定）
5. IPDB API（通用优选，大量104段）
6. 本地实测IP池（兜底）

#### CDN优选IP评分规则（v2.0.0 - Bug #41教训重构）

**评分公式：总分 = 数据源可信度分 + 排名加分 + 交叉验证加分 + IP段参考分**

**数据源可信度权重：**
| 数据源 | 权重 | 说明 |
|--------|------|------|
| vvhan API | +30 | 中国实测，含延迟/速度/数据中心，每15分钟更新 |
| 090227 API | +25 | 中国电信实测，纯162.159段 |
| 001315 API | +15 | 中国电信实测，混合段（含8.39段） |
| WeTest DNS | +10 | DoH解析，质量不稳定 |
| IPDB API | +5 | 通用优选，大量104段 |
| 本地池 | +0 | 兜底 |

**IP段参考分（软参考，不硬过滤）：**
| IP段 | 分数 | 说明 |
|------|------|------|
| 162.159.x.x | +10 | 用户实测最优段，50-53ms |
| 108.162.x.x | +10 | 用户实测最优段，50-51ms |
| 172.64.x.x | +8 | 用户实测优质段，50-53ms |
| 173.245.x.x | +8 | vvhan电信推荐，50-55ms |
| 198.41.x.x | +8 | vvhan电信推荐，50-55ms |
| 104.16-21.x.x | -10 | 实测延迟高(66-130ms)，降权但不丢弃 |
| 8.39/8.35.x.x | -5 | 实测数据不支持，降权 |

**交叉验证加分：** 同一IP被N个数据源推荐，额外+(N-1)×15分

**核心改变（v2.0.0 vs v1.0.85）：**
- v1.0.85：按IP段前缀硬过滤，104段直接丢弃，8.39段直接丢弃
- v2.0.0：综合评分排序，104段降权但不丢弃，8.39段降权但不丢弃
- 优势：不再一刀切，多源交叉验证的IP质量更可靠

#### CDN数据源详细调研记录（v2.0.0 新增，供后续AI/开发者参考）

> 以下内容记录了v2.0.0重构时对所有CDN优选IP数据源的调研过程。
> 包括每个API的地址、返回格式、实际返回示例、质量评估、可信度评分依据。
> **目的**：让后续接手的AI或开发者能理解"为什么这样评分"，而不是盲目调参。

##### 数据源1：vvhan API（可信度最高，+30分）

- **API地址**：`https://api.vvhan.com/tool/cf_ip`
- **展示页面**：`https://cf.vvhan.com/`
- **更新频率**：每15分钟
- **返回格式**：JSON
- **返回示例**（2026-04-25实测）：
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
- **电信实测IP**（2026-04-25 07:00:00）：
  - 108.162.196.94 → SIN(新加坡)
  - 108.162.193.55 → SIN
  - 162.159.26.40 → SIN
  - 108.162.192.188 → SIN
  - 162.159.5.112 → SIN
- **联通实测IP**：162.159.11.x → LAX(洛杉矶)
- **移动实测IP**：104.26.7.x → SEA(西雅图)
- **为什么可信度最高**：
  1. 返回JSON格式，包含延迟(latency)、速度(speed)、数据中心(colo)信息
  2. 按运营商分类（CT电信/CM移动/CU联通），可精确匹配目标用户群
  3. 每15分钟更新，数据时效性最好
  4. 电信推荐IP全部走SIN(新加坡)节点，与用户实测数据一致
  5. 基于 XIU2/CloudflareSpeedTest 工具实测，方法论可靠
- **代码解析方式**：`fetch_from_vvhan_ct()` 解析JSON，提取 `data.v4.CT` 列表

##### 数据源2：090227电信API（可信度第二，+25分）

- **API地址**：`https://addressesapi.090227.xyz/ct`
- **其他线路**：`/cm`(移动) `/cu`(联通)
- **返回格式**：纯文本，每行 `IP#运营商`
- **返回示例**（2026-04-25实测）：
```
162.159.153.144#CT
162.159.153.156#CT
162.159.153.72#CT
162.159.152.31#CT
162.159.153.170#CT
162.159.153.216#CT
```
- **特点**：
  1. 返回纯162.159.x.x段IP，与用户实测最优段完全一致
  2. IP排序=中国电信实测延迟从低到高
  3. 格式简单，解析方便（`line.split('#')[0]`）
- **为什么排第二**：不含延迟/速度等详细信息，无法做更精细的筛选
- **代码解析方式**：`fetch_from_090227_ct()` 按行解析，提取#前的IP

##### 数据源3：001315电信API（可信度第三，+15分）

- **API地址**：`https://cf.001315.xyz/ct`
- **其他线路**：`/cm`(移动) `/cu`(联通)
- **返回格式**：纯文本，每行 `IP#运营商`
- **返回示例**（2026-04-25实测）：
```
8.39.125.195#电信
173.245.59.30#电信
162.159.33.148#电信
8.39.125.139#电信
173.245.59.55#电信
8.39.125.28#电信
```
- **特点**：
  1. 返回混合段IP：8.39/173.245/162.159
  2. IP排序=中国电信实测延迟从低到高
  3. 8.39段排在前面，但实测数据不支持其为优质段
- **为什么排第三**：
  - 8.39段IP排在前面但未被其他数据源验证
  - 173.245段是优质段，与vvhan/090227交叉验证一致
  - 162.159段也是优质段
  - 综合来看：部分IP可信，但8.39段存疑，所以权重低于090227
- **v2.0.0改进**：不再硬过滤8.39段，而是通过IP段参考分(-5)降权，如果8.39段IP被其他源交叉验证推荐，仍有机会入选
- **代码解析方式**：`fetch_from_001315_ct()` 按行解析，提取#前的IP

##### 数据源4：WeTest DNS（可信度第四，+10分）

- **DNS地址**：`ct.cloudflare.182682.xyz`（电信优选）
- **其他线路**：`cm.cloudflare.182682.xyz`(移动) `cu.cloudflare.182682.xyz`(联通)
- **展示页面**：`https://www.wetest.vip/page/cloudflare/address.html`
- **返回格式**：DNS A记录，需通过DNS解析获取IP
- **解析方式**：必须用DoH(DNS over HTTPS)从境外服务器解析
  - 正确DoH：`https://dns.alidns.com/resolve?name=ct.cloudflare.182682.xyz&type=A`
  - 错误方式：直接dig @8.8.8.8（返回104段，Bug #27教训）
- **为什么可信度低**：
  1. DNS记录本身可能返回104.18.x.x段（即使用中国DNS解析也是104段）
  2. 104段对中国用户延迟130ms+（Bug #29教训）
  3. DNS解析结果不如API排序精确
- **代码解析方式**：`fetch_from_wetest_ct()` 通过DoH解析获取IP列表

##### 数据源5：IPDB API（可信度第五，+5分）

- **API地址**：`https://ipdb.api.030101.xyz/?type=bestcf`
- **返回格式**：纯文本，每行一个IP
- **返回示例**（2026-04-25实测）：
```
104.16.144.115
104.17.145.73
104.17.210.105
172.64.155.57
104.19.38.170
198.41.209.203
```
- **为什么可信度最低**：
  1. 大量104.16-19段IP，对中国延迟高
  2. 不按运营商分类，返回的是通用"bestcf"
  3. 172.64/198.41段偶有优质IP，但占比极低
- **代码解析方式**：`fetch_from_ipdb_api()` 按行解析纯IP

##### 数据源6：本地实测IP池（兜底，+0分）

- **定义位置**：`config.py` 的 `CDN_PREFERRED_IPS` 列表
- **用途**：所有外部API不可用时的最后兜底
- **更新方法**：
  1. 访问 `https://cf.vvhan.com/` 查看电信推荐IP
  2. 访问 `https://cf-ip.cdtools.click/beijing` 查看北京地区测速结果
  3. 使用 XIU2/CloudflareSpeedTest 工具从中国网络实测
  4. 只选取162.159/172.64/108.162/173.245/198.41段的IP
  5. 按延迟从低到高排列
  6. 同步更新config.py和cdn_monitor.py的ImportError降级块

##### 其他已知数据源（未使用，备查）

| 数据源 | 地址 | 说明 | 未使用原因 |
|--------|------|------|-----------|
| stock.hostmonit.com | `https://stock.hostmonit.com/CloudFlareYes` | 返回HTML表格含延迟/丢包/速度 | 解析复杂，数据量少 |
| cf-ip.cdtools.click | `https://cf-ip.cdtools.click/beijing` | 按城市测速，含延迟/丢包/速度 | 无API接口，仅HTML展示 |
| monitor.gacjie.cn | `https://monitor.gacjie.cn/api/client/get_ip_address` | JSON格式含延迟 | 响应不稳定 |
| ip.164746.xyz | `https://ip.164746.xyz` | CF优选IP | 返回HTML无结构化数据 |
| ip.haogege.xyz | `https://ip.haogege.xyz` | CF优选IP | 返回HTML无结构化数据 |
| api.uouin.com | `https://api.uouin.com/cloudflare.html` | CF优选IP | 返回HTML无结构化数据 |

##### 评分逻辑推导过程

**问题**：从日本服务器无法直接测出对中国用户的延迟和带宽（因为距离CF节点太近，TCPing都是1-2ms），所以必须依赖从中国实测的第三方API。

**旧方案（v1.0.85）的问题**：
- 按IP段前缀硬过滤（`is_hunan_ct_optimal()`），162.159/172.64=优质，104段=丢弃
- 001315 API返回的8.39段被直接丢弃，但8.39段可能是中国电信实测排序的
- 单一数据源依赖（090227优先），API挂了就降级到不可靠源
- 没有交叉验证，无法区分"多个源都推荐的IP"和"只有一个源推荐的IP"

**新方案（v2.0.0）的推导**：
1. 既然无法从服务器端实测，那就信任从中国实测的API排序
2. 不同API的可信度不同：vvhan含延迟数据 > 090227纯162.159段 > 001315含8.39段
3. 如果一个IP被多个API同时推荐，说明它的质量确实好（交叉验证）
4. IP段前缀作为参考因素但不硬过滤：104段大概率差(-10分)，但不排除个别好IP
5. 最终按综合评分排序，选TOP N

**评分公式各参数的取值依据**：
- 数据源权重(30/25/15/10/5/0)：拉开差距，确保高可信源优先
- 排名加分(20/18/16...)：API排序本身就是实测结果，排名靠前的应该加分
- 交叉验证(+15/源)：被2个源推荐+15，3个源+30，确保交叉验证有足够权重
- IP段参考分(+10/+8/-10/-5)：基于历史实测数据，但不硬过滤

**模拟验证结果**（2026-04-25）：
```
场景1：各源返回不同IP
  #1: 108.162.196.94 (评分=60, 来源=vvhan)
  #2: 108.162.193.55 (评分=58, 来源=vvhan)
  #3: 162.159.26.40  (评分=56, 来源=vvhan)
  #4: 162.159.153.144 (评分=55, 来源=090227)
  #5: 108.162.192.188 (评分=54, 来源=vvhan)

场景2：交叉验证（162.159.26.40被3个源推荐）
  162.159.26.40 | 总分=170 (源=70 排名=60 交叉=30 段=10) | vvhan+090227+001315 x3
  162.159.5.112 | 总分=116 (源=55 排名=36 交叉=15 段=10) | vvhan+090227 x2
  162.159.153.144 | 总分=51 (源=25 排名=16 交叉=0 段=10) | 090227
```

### 4. SOCKS5 AI路由
- 触发: 配置AI_SOCKS5_SERVER后自动生效
- AI网站走SOCKS5: openai/anthropic/gemini/perplexity/google等
- X/推特/groK排除: 走直连
- 幕后路由，用户无需手动选择

### 5. 按月流量统计
- 每次订阅请求自动累加（/sub和/singbox路由均统计）
- 每月14号自动归零
- API: `/api/traffic`（返回JSON）
- 首页蓝色流量统计区域
- **subscription-userinfo响应头**（v2.0.0新增，Bug #42修复）：
  - /sub和/singbox路由的HTTP响应头包含`subscription-userinfo`
  - 格式：`upload=0; download={bytes_used}; total=-1; expire=0`
  - 客户端（v2rayN/Clash/Shadowrocket等）通过此头显示流量信息
  - upload=0：上传流量不统计
  - download={bytes_used}：当月已用下载流量（字节）
  - total=-1：总流量不限
  - expire=0：永不过期

### 6. SSL证书
- 优先级: fullchain.pem > cert.pem
- 自动续签: acme.sh + cron（每月1号凌晨3点）
- 所有引用点统一路径

### 7. BBR+FQ+CAKE网络加速
- BBR: Google拥塞控制，不依赖丢包
- FQ: 公平队列，BBR的pacing依赖
- CAKE: 集成FQ+PIE，防缓冲区膨胀，抗丢包
- 降级: 内核不支持CAKE时自动降级FQ-PIE（tc qdisc replace实际应用到网卡）
- CAKE模块主动安装: modprobe失败时自动安装linux-modules-extra
- 持久化: systemd服务（cake-qdisc@ / fq-pie-qdisc@）
- 即时生效，无需重启

### 8. 安装脚本子命令
- `bash install.sh` — 全新安装
- `bash install.sh reinstall` — 重装操作系统（需root密码）
- `bash install.sh reset` — 重装singbox应用（保留配置）
- `bash install.sh optimize` — 一键优化系统

### 9. sing-box rule_set（1.12+格式）
- geoip/geosite已移除，改用rule_set远程.srs规则集
- 客户端: geosite-cn.srs / geoip-cn.srs / geosite-geolocation-!cn.srs
- 服务端: 不需要geoip/geosite（catch-all处理direct）

---

## 五、.env 配置

### 必填
| 变量 | 说明 |
|------|------|
| SERVER_IP | 服务器IP（留空自动检测） |
| CF_DOMAIN | Cloudflare域名 |

### 协议密码（安装时自动生成）
| 变量 | 说明 |
|------|------|
| VLESS_UUID | VLESS Reality UUID |
| VLESS_WS_UUID | VLESS WS/HTTPUpgrade UUID |
| TROJAN_PASSWORD | Trojan-WS密码 |
| HYSTERIA2_PASSWORD | Hysteria2密码 |
| REALITY_PRIVATE_KEY | Reality私钥 |
| REALITY_PUBLIC_KEY | Reality公钥 |

### 可选
| 变量 | 说明 |
|------|------|
| CF_API_TOKEN | Cloudflare API Token（证书申请） |
| COUNTRY_CODE | 国家代码（自动检测） |
| SUB_TOKEN | 订阅Token |
| AI_SOCKS5_SERVER | AI SOCKS5服务器 |
| AI_SOCKS5_PORT | AI SOCKS5端口 |
| AI_SOCKS5_USER | AI SOCKS5用户名 |
| AI_SOCKS5_PASS | AI SOCKS5密码 |
| TG_BOT_TOKEN | Telegram Bot Token |
| TG_ADMIN_CHAT_ID | 管理员Chat ID |

---

## 六、编码铁律（避坑指南）

### 规则1：HTTPS订阅必须用域名访问，禁止用IP
**教训**: v1.0.43用IP访问HTTPS订阅，V2rayN验证SSL证书时发现证书颁发给域名，与IP不匹配，拒绝连接（SEC_E_WRONG_PRINCIPAL）
**做法**: 订阅链接必须用域名格式 `https://{CF_DOMAIN}:{SUB_PORT}/sub/{CC}`

### 规则2：订阅端口必须在Cloudflare CDN支持列表
**教训**: v1.0.43用9443端口，CDN不代理，域名访问时CDN直接丢弃流量
**CDN支持HTTPS端口**: 443, 2053, 2083, 2087, 2096, 8443

### 规则3：HY2端口跳跃必须UDP+TCP双规则，目标端口与listen_port一致
**教训**: v1.0.45前DNAT到4433但HY2监听443（端口跳跃无效）；后来修复时又错误移除TCP规则（UDP被封则HY2完全不可用）
**做法**: iptables DNAT目标必须与config_generator.py的listen_port一致，必须同时设UDP+TCP

### 规则4：CDN IP获取必须用指定DNS
**教训**: v1.0.36-37用日本服务器DNS解析，返回对中国延迟高的IP（200ms+）
**做法**: 使用222.246.129.80 / 59.51.78.210（湖南电信DNS），或阿里DoH(dns.alidns.com)
**Bug #29补充**: WeTest.vip即使用中国DNS解析也返回104.x.x.x段（130ms+），必须过滤后丢弃，不能"全部保留"
**Bug #29补充**: 境外服务器必须用DoH方式解析，直接dig中国DNS会超时

### 规则5：测试必须模拟真实客户端环境
**教训**: v1.0.43用curl -k测试通过，但V2rayN不用-k，验证证书失败
**做法**: 测试HTTPS服务禁止-k/--insecure

### 规则6：禁止硬编码IP/域名/凭据/路径
**教训**: v1.0.45前大量硬编码，新VPS部署必须手动改代码，极易遗漏
**做法**: 所有IP/域名从.env读，路径从config.py拼，凭据从环境变量读

### 规则7：修改配置必须全局搜索所有引用文件
**教训**: v1.0.50发现13个隐藏问题，根因是改subscription_service.py时没同步改config_generator.py/tg_bot.py/README.md
**做法**: 修改前 `grep -r "关键词" scripts/ *.md`，统一引用config.py作为唯一真相源

### 规则8：服务重启必须覆盖所有相关服务
**教训**: v1.0.52设置住宅后只重启singbox+singbox-sub，漏了singbox-cdn
**做法**: 重启必须 singbox + singbox-sub + singbox-cdn

### 规则9：AI-SOCKS5是幕后路由出站，不是用户可见节点
**教训**: v1.0.48把AI-SOCKS5当成"节点"加入Base64订阅和selector，用户手动选择后无法正常使用
**做法**: 禁止将幕后路由出站加入订阅链接、selector、首页节点列表

### 规则10：改代码必须同步更新文档
**教训**: 多次出现"代码改了文档没改"，导致下一个AI基于过时文档犯错
**做法**: 改代码后必须同步更新TECHNICAL_DOC.md，版本号+1

### 规则11：防火墙重置必须在端口跳跃之前
**教训**: v1.0.52中iptables -F清空了刚设置的端口跳跃规则
**做法**: 安装脚本执行顺序：端口跳跃 → 防火墙 → 服务启动

### 规则12：降级方案必须实际应用到网卡
**教训**: v1.0.75前CAKE降级只设sysctl参数，未通过tc qdisc replace应用到网卡，降级也不生效
**做法**: 降级必须 `tc qdisc replace dev $MAIN_IF root fq_pie`，不能只设sysctl

### 规则13：订阅链接不加token认证
**做法**: 保持原有规则直接访问

### 规则14：数据库连接必须在finally中关闭
**教训**: v1.0.54前数据库连接泄漏
**做法**: try/finally确保conn.close()

### 规则15：异常信息禁止返回给用户
**教训**: cdn_api()的500错误返回str(e)，可能泄露内部路径/SQL语句
**做法**: logger.error记录详细日志，返回通用'Internal server error'

### 规则16：禁止裸except
**做法**: 必须指定Exception，否则会吞掉KeyboardInterrupt/SystemExit

### 规则17：ImportError降级必须定义所有必需变量
**教训**: config.py导入失败时except块只定义了get_logger，后续代码引用SERVER_IP等变量时NameError导致服务无法启动
**做法**: except块中定义所有必需变量的降级值

### 规则18：小内存VPS必须配Swap
**教训**: 414MB内存无Swap，OOM killer杀掉singbox进程导致掉线（Bug #39）
**做法**: <1GB内存的VPS必须创建2GB Swap，禁用fwupd/snapd等不必要的服务

### 规则19：日志必须配logrotate
**教训**: singbox日志12MB+且持续增长，无轮转机制（运维#1）
**做法**: /etc/logrotate.d/singbox 配置 daily + rotate 7 + maxsize 50M

---

## 七、Bug修复历史

| # | 版本 | 问题 | 根因 | 修复 |
|---|------|------|------|------|
| 1 | v1.0.39 | Trojan-WS链接缺少insecure=1 | 缺少参数 | 添加insecure=1和allowInsecure=1 |
| 2 | v1.0.37 | CDN优选IP对中国延迟高 | 日本DNS返回不友好IP | 恢复固定优选IP池 |
| 3 | v1.0.41 | Trojan-WS协议不通 | 缺SSL配置+path编码不一致 | 添加SSL+统一URL编码 |
| 4 | v1.0.42 | 订阅端口9443不通 | 默认端口/防火墙/CDN三重bug | 端口6969→9443+防火墙放行 |
| 5 | v1.0.44 | V2rayN无法更新订阅 | IP访问HTTPS证书不匹配 | 9443→2087走CDN+域名访问 |
| 6 | v1.0.45 | 新VPS部署困难 | 大量硬编码 | 全面消除硬编码+config.py统一 |
| 7 | v1.0.45 | CDN优选IP过期 | 固定IP池+随机ping | 改指定DNS解析+4级降级 |
| 8 | v1.0.45 | HY2端口跳跃目标错误 | DNAT到4433但HY2监听443 | 目标改为443 |
| 9 | v1.0.49 | AI-SOCKS5暴露为用户节点 | 当成普通节点加入订阅 | 移除订阅链接和selector |
| 10 | v1.0.50 | 跨文件配置不一致 | 修改时未全局搜索 | 统一引用config.py |
| 11 | v1.0.50 | HY2端口范围错误+缺TCP | iptables 22000 vs config 21000 | 统一21000-21200+补TCP |
| 12 | v1.0.52 | 证书文件名不一致 | cert.crt vs cert.pem | 统一cert.pem+fullchain.pem |
| 13 | v1.0.52 | 防火墙清除端口跳跃规则 | iptables -F在规则之后 | 调整执行顺序 |
| 14 | v1.0.52 | TG机器人CDN更新死循环 | cdn_monitor.py是无限循环 | 改为import单次执行 |
| 15 | v1.0.52 | 设置住宅后不重启singbox-cdn | 漏了singbox-cdn | 添加systemctl restart |
| 16 | v1.0.52 | HY2端口范围硬编码覆盖 | subscription_service.py独立定义 | 删除，用config.py导入 |
| 17 | v1.0.71 | CAKE状态显示矛盾 | print_summary硬编码已启用 | 改为tc qdisc实际检测 |
| 18 | v1.0.72 | reinstall声称不需密码 | 混淆应用密码和root密码 | 改为需输入root密码 |
| 19 | v1.0.66 | set -e导致CAKE失败脚本退出 | tc qdisc返回非零码 | 改为cmd && OK || true |
| 20 | v1.0.74 | geoip/geosite在1.12+移除 | sing-box FATAL退出 | 改用rule_set格式 |
| 21 | v1.0.74 | CAKE降级FQ不如FQ-PIE | 选了最基础降级方案 | fq→fq_pie |
| 22 | v1.0.75 | CAKE降级仅设sysctl未应用 | 未tc qdisc replace到网卡 | 新增setup_fq_pie_qdisc()+主动安装模块 |
| 23 | v1.0.76 | DNS代理查询延迟飙升 | dns_proxy走ePS-Auto | detour改为direct |
| 24 | v1.0.77 | CDN优选IP不自动更新 | 本地池永远优先 | 外部API优先于本地池 |
| 25 | v1.0.78 | X/推特/groK走SOCKS5 | AI规则在排除规则之前 | 排除规则移到AI规则之前 |
| 26 | v1.0.78 | SOCKS5无故障转移 | selector无fallback | 加direct作为第二选项 |
| 28 | v1.0.82 | AI规则含google.com延迟高 | v2rayN测速走SOCKS5 | 移除通用google域名 |
| 29 | v1.0.82 | CDN返回104段高延迟 | WeTest返回104段 | 001315优先+104段严格过滤 |
| 30 | v1.0.82 | config_generator与sub不同步 | 改A忘B | 两个文件必须同步更新 |
| 31 | v1.0.82 | CDN优选IP更新服务卡住 | time.sleep卡住 | crontab每小时重启singbox-cdn |
| 32 | v1.0.83 | config_generator缺DNS和final | 从未添加 | 添加DNS+final:direct |
| 33 | v1.0.83 | S-UI残留进程和目录 | 只stop/disable | 删服务文件+目录+杀进程 |
| 34 | v1.0.84 | CDN重启crontab未写入install.sh | Bug #31修复只在服务器 | install.sh加crontab兜底 |
| 35 | v1.0.85 | CDN本地池混入104.x.x.x高延迟IP | 本地池未过滤104段 | 移除104段，替换为162.159/172.64段 |
| 36 | v1.0.85 | cert_manager续签后漏重启singbox-cdn | restart_singbox()漏服务 | 加singbox-cdn重启 |
| 37 | v1.0.85 | health_check漏检UDP端口(HY2) | 只检查TCP端口 | 增加UDP 443检查 |
| 38 | v1.0.85 | cdn_monitor数据库连接泄漏 | conn.close()不在finally | 改try/finally |
| 39 | v1.0.85 | 414MB内存无Swap，OOM杀进程 | 无Swap+fwupd占144MB | 创建2GB Swap+禁用fwupd |
| 40 | v1.0.85 | HUNAN_CT_OPTIMAL_PREFIXES含未验证段 | 8.39/8.35实测不支持 | 移除8.39/8.35，001315也加过滤 |

---

## 八、版本历史

| 版本 | 日期 | 更新 |
|------|------|------|
| v1.0.34 | 04-20 | HTTPS订阅+Cloudflare证书+端口9443 |
| v1.0.38 | 04-20 | sing-box JSON配置+AI流量路由 |
| v1.0.42 | 04-21 | 订阅端口9443不通修复 |
| v1.0.44 | 04-21 | V2rayN订阅失败→2087走CDN+域名访问 |
| v1.0.45 | 04-21 | 全面消除硬编码+DNS优选CDN |
| v1.0.47 | 04-21 | HY2端口跳跃无感切换 |
| v1.0.49 | 04-21 | 修复AI-SOCKS5暴露为用户节点 |
| v1.0.50 | 04-21 | 全面排查13个隐藏坑+跨文件一致性 |
| v1.0.52 | 04-21 | 证书文件名统一+自动续签cron+防火墙顺序 |
| v1.0.54 | 04-21 | subscription_service.py安全加固 |
| v1.0.60 | 04-22 | 按月流量统计 |
| v1.0.65 | 04-22 | BBR+FQ+CAKE三合一加速 |
| v1.0.66 | 04-22 | 修复set -e导致CAKE失败脚本退出 |
| v1.0.72 | 04-22 | reinstall改为操作系统重装+root密码确认 |
| v1.0.74 | 04-22 | geoip/geosite改rule_set+CAKE降级改FQ-PIE |
| v1.0.75 | 04-22 | CAKE模块主动安装+FQ-PIE实际应用到网卡+精确诊断 |
| v1.0.84 | 04-24 | CDN每小时crontab重启兜底+JSUI清理+版本号统一 |
| v1.0.85 | 04-25 | 修复CDN本地池104段+cert漏重启+UDP端口检查+DB连接泄漏+OOM/Swap+8.39/8.35段 |
| v2.0.0 | 04-25 | CDN优选IP重构：多源聚合+综合评分排序，新增vvhan API，不再硬过滤IP段，订阅添加subscription-userinfo头 |
| v3.0.0 | 04-25 | CDN学习系统：IP性能数据库+综合评分+自动淘汰+用户投喂 |
| v3.0.1 | 04-26 | 三层自愈机制+进程锁防泄漏+VPS内存优化(244MB→181MB)+禁用无用服务 |

---

## 九、使用说明

### 安装脚本子命令
| 命令 | 功能 |
|------|------|
| `bash install.sh` | 全新安装（自动优化系统+交互式配置） |
| `bash install.sh reinstall` | 重装操作系统（需root密码，装完自动重启） |
| `bash install.sh reset` | 重装singbox应用（保留配置和数据，客户端无需重配） |
| `bash install.sh optimize` | 一键优化系统（BBR+FQ+CAKE三合一，即时生效） |

### 服务管理
```bash
systemctl restart singbox singbox-sub singbox-cdn  # 重启所有服务
systemctl status singbox singbox-sub singbox-cdn   # 查看状态
journalctl -u singbox-sub -f                       # 查看日志
```

### 证书管理
```bash
python3 /root/singbox-eps-node/scripts/cert_manager.py --cf-cert  # Cloudflare API申请15年证书
python3 /root/singbox-eps-node/scripts/cert_manager.py --renew    # 手动续签
```

### CDN优选IP手动更新
```bash
python3 /root/singbox-eps-node/scripts/cdn_monitor.py
```

### 健康检查
```bash
bash /root/singbox-eps-node/scripts/health_check.sh  # 手动运行
```
每5分钟自动运行，检查端口/服务/订阅/防火墙/证书/磁盘。

### 流量统计
- 首页: `https://{域名}:2087/`
- API: `https://{域名}:2087/api/traffic`
- 重置: 每月14号自动归零

### Telegram机器人
在.env中配置 `TG_BOT_TOKEN` 和 `TG_ADMIN_CHAT_ID`，可用命令：/状态 /续签 /订阅 /重启 /优选 /设置住宅 /删除住宅

### 卸载
```bash
systemctl stop singbox singbox-sub singbox-cdn
systemctl disable singbox singbox-sub singbox-cdn
rm /etc/systemd/system/singbox*.service /etc/systemd/system/cake-qdisc*.service /etc/systemd/system/fq-pie-qdisc*.service
systemctl daemon-reload
rm -rf /root/singbox-eps-node
netfilter-persistent save
```
