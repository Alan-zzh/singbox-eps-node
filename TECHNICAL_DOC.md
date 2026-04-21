# 技术文档 - 供其他AI审查

## 项目概述
- **项目名称**: Singbox EPS Node (代理节点订阅系统)
- **服务器**: 从.env动态读取SERVER_IP（自动检测公网IP）
- **域名**: 从.env动态读取CF_DOMAIN（用于CDN和SSL证书）
- **当前版本**: v1.0.62

---

## 当前架构

### 服务列表
| 服务 | 端口 | 协议 | 状态 |
|------|------|------|------|
| singbox主服务 | 443, 8443, 2053, 2083 | TCP/UDP | ✅ active |
| singbox-sub订阅 | 2087 | HTTPS (CDN支持) | ✅ active |
| singbox-cdn监控 | - | 定时任务(每小时) | ✅ active |

### 节点列表（5个用户可见节点 + 1个幕后路由出站）
1. **{CC}-VLESS-Reality**: {SERVER_IP}:443 (直连，Reality协议)
2. **{CC}-VLESS-WS-CDN**: Cloudflare优选IP:8443 (CDN)
3. **{CC}-VLESS-HTTPUpgrade-CDN**: Cloudflare优选IP:2053 (CDN)
4. **{CC}-Trojan-WS-CDN**: Cloudflare优选IP:2083 (CDN)
5. **{CC}-Hysteria2**: {SERVER_IP}:443 (直连，端口跳跃21000-21200→443)

⚠️ **AI-SOCKS5不是用户可见节点，是幕后路由出站**：
- 不出现在Base64订阅链接中
- 不出现在ePS-Auto selector的可选列表中
- 仅出现在sing-box JSON的outbounds（ai-residential）和route.rules中
- 用户在客户端节点列表中看不到AI-SOCKS5
- AI网站流量自动走SOCKS5，用户无感，无需手动选择

---

## 已完成功能

### 1. HTTPS订阅服务 ✅
- **订阅链接**: `https://{CF_DOMAIN}:2087/sub/{CC}`（域名访问，走CDN）
- **sing-box JSON**: `https://{CF_DOMAIN}:2087/singbox/{CC}`（含自动路由规则）
- **证书**: Let's Encrypt正式证书（acme.sh + Cloudflare DNS API）
- **端口**: 2087（Cloudflare CDN支持的端口）
- **自动续期**: acme.sh已配置
- ⚠️ **禁止用IP访问**: IP访问导致SSL证书域名不匹配

### 2. Hysteria2端口跳跃 ✅
- **实现方式**: iptables DNAT规则 + 客户端hop_ports字段
- **服务端规则**: 
  - UDP: `iptables -t nat -A PREROUTING -p udp --dport 21000:21200 -j DNAT --to-destination :443`
  - TCP: `iptables -t nat -A PREROUTING -p tcp --dport 21000:21200 -j DNAT --to-destination :443`
- **客户端配置**: `"hop_ports": "21000-21200"`（sing-box JSON）或 `mport=443,21000-21200`（Base64链接）
- **无感切换原理**: 客户端初始连443，后续QUIC连接自动在21000-21200范围内跳跃，服务端iptables全部DNAT到443，某个端口被封自动跳到其他端口，无需断线重连
- **双协议保障**: UDP是HY2核心(QUIC)，TCP是降级兜底(UDP被封时)
- **持久化**: `/etc/iptables/rules.v4`
- **规避措施**:
  - obfs=salamander：规避QUIC/UDP流量特征检测
  - obfs-password：取HY2密码前8位
  - 端口跳跃21000-21200：扩大端口范围规避封锁，无感切换不掉线
  - alpn=["h3"]：HY2使用QUIC协议

### 3. CDN优选IP ✅
- **机制**: 4级降级保障，确保主方案失效时自动切换备选方案
- **4级降级策略（按优先级自动切换）**:
  1. 本地实测IP池（CDN_PREFERRED_IPS）— 湖南电信实测最优IP，按延迟排序
  2. cf.001315.xyz/ct电信API — 返回 `IP#电信` 格式，按运营商分类
  3. WeTest.vip电信优选DNS（ct.cloudflare.182682.xyz）— 按运营商分类，每15分钟更新
  4. IPDB API bestcf — 通用优选IP，不按运营商分类
- **湖南电信最优IP段筛选**:
  - 162.159.x.x / 172.64.x.x / 108.162.x.x 段延迟50-53ms（最优）
  - 198.41.x.x / 173.245.x.x 段延迟50-55ms（次优）
  - 104.16-21.x.x 段延迟130ms+（必须过滤）
- **自动切换逻辑**: 主方案不可达→备选1→备选2→备选3→降级IP池
- **存储**: SQLite数据库（data/singbox.db）
- **分配**: 每个CDN协议独立优选IP
- **更新频率**: 每小时自动查询+TCPing验证

### 4. SOCKS5 AI路由规则 ✅
- **实现方式**: sing-box路由规则自动分流
- **出站标签**: `ai-residential`（SOCKS5代理）
- **触发条件**: 配置了AI_SOCKS5_SERVER和AI_SOCKS5_PORT环境变量时自动生效
- **AI网站自动走SOCKS5**（无感路由，用户无需手动选择）:
  - openai.com, chatgpt.com
  - anthropic.com, claude.ai
  - gemini.google.com, bard.google.com, ai.google, aistudio.google.com
  - perplexity.ai
  - midjourney.com, stability.ai
  - cohere.com, replicate.com
  - google.com, googleapis.com, gstatic.com
  - 关键词: openai, anthropic, claude, gemini, perplexity, aistudio
- **X/推特/groK排除**（不走SOCKS5，走直连）:
  - x.com, twitter.com, twimg.com, t.co, x.ai, grok.com
  - 关键词: twitter, grok
- **sing-box配置**: 条件生成outbound（ai-residential）+ 路由规则
- **未配置时**: 不生成任何SOCKS5相关节点和规则，不影响其他节点
- ⚠️ **AI-SOCKS5是幕后路由出站，不是用户可见节点**：
  - 禁止将AI-SOCKS5加入Base64订阅链接
  - 禁止将AI-SOCKS5加入ePS-Auto selector的可选列表
  - 用户在客户端节点列表中不应看到AI-SOCKS5

### 5. 按月流量统计 ✅
- **数据库表**: traffic_stats（key-value结构，与cdn_settings一致）
- **统计方式**: 每次订阅请求返回时自动累加响应数据量
- **自动归零**: 每月14号自动归零（检查当天日期+本月是否已重置过）
- **持久化**: 数据存储在data/singbox.db，重装系统才丢失
- **API接口**: `/api/traffic` 返回JSON格式流量数据（不加token认证，铁律13）
- **首页显示**: 首页蓝色流量统计区域，显示当月已用流量+统计月份+归零日

### 6. SSL证书路径统一 ✅
- **证书文件名统一规则**:
  - cert_manager.py生成: cert.pem + key.pem（自签名/Cloudflare API）
  - acme.sh生成: fullchain.pem + key.pem（Let's Encrypt）
- **优先级**: fullchain.pem > cert.pem（fullchain.pem包含完整证书链）
- **所有引用点统一**:
  - subscription_service.py: 优先fullchain.pem，降级cert.pem
  - config_generator.py: 优先fullchain.pem，降级cert.pem
  - health_check.sh: 循环检查fullchain.pem和cert.pem
  - cert_manager.py: check_cert_expiry()循环检查fullchain.pem和cert.pem

---

## 配置管理

### .env 必需变量
```
SERVER_IP=          # 服务器公网IP（留空则自动检测）
CF_DOMAIN=          # Cloudflare域名（用于CDN和SSL证书）
VLESS_UUID=         # VLESS-Reality UUID
VLESS_WS_UUID=      # VLESS-WS/HTTPUpgrade UUID
TROJAN_PASSWORD=    # Trojan-WS密码
HYSTERIA2_PASSWORD= # Hysteria2密码
REALITY_PRIVATE_KEY=# Reality私钥
REALITY_PUBLIC_KEY= # Reality公钥
CF_API_TOKEN=       # Cloudflare API Token（证书申请用）
COUNTRY_CODE=JP     # 国家代码
SUB_TOKEN=          # 订阅Token（可选）
AI_SOCKS5_SERVER=   # AI SOCKS5服务器（可选，配置后AI路由自动生效）
AI_SOCKS5_PORT=     # AI SOCKS5端口（可选）
AI_SOCKS5_USER=     # AI SOCKS5用户名（可选）
AI_SOCKS5_PASS=     # AI SOCKS5密码（可选）
```

### 端口分配
```
443    - singbox VLESS-Reality + Hysteria2入站
2053   - singbox VLESS-HTTPUpgrade-CDN入站
2083   - singbox Trojan-WS-CDN入站
2087   - Flask订阅服务（HTTPS，CDN支持）
8443   - singbox VLESS-WS-CDN入站
1080   - singbox SOCKS5本地代理
21000-21200 - Hysteria2端口跳跃（iptables DNAT → 443, UDP+TCP）
```

### 文件路径
```
/root/singbox-eps-node/
├── .env                           # 环境变量（所有配置集中管理）
├── config.json                    # singbox配置
├── cert/                          # SSL证书
│   ├── cert.pem                   # Let's Encrypt证书
│   ├── key.pem                    # 私钥
│   └── fullchain.pem              # 完整证书链
├── data/
│   ├── singbox.db                 # SQLite数据库（CDN IP等）
│   └── .port_lock                 # 端口锁定文件（防篡改）
├── scripts/
│   ├── config.py                  # 全局配置（自动检测IP+统一读取.env）
│   ├── logger.py                  # 日志管理
│   ├── cdn_monitor.py             # CDN监控（指定DNS解析+降级方案）
│   ├── subscription_service.py    # 订阅服务（HTTPS，消除硬编码）
│   ├── config_generator.py        # 配置生成器（消除硬编码路径）
│   ├── cert_manager.py            # 证书管理+HY2端口跳跃
│   ├── tg_bot.py                  # Telegram机器人
│   └── health_check.sh            # 健康检查与自动恢复（每5分钟）
├── logs/
│   └── health_check.log           # 健康检查日志
└── backups/                       # 备份目录
```

---

## 待解决问题

（当前无待解决问题）

---

## 给其他AI的建议

1. **修改代码前**: 先查阅 `project_snapshot.md` 和 `AI_DEBUG_HISTORY.md` 了解当前状态和已踩过的坑
2. **禁止硬编码**: 所有IP、域名、端口、密码必须从.env读取，禁止在代码中硬编码
3. **HTTPS订阅必须用域名**: SSL证书颁发给域名，IP访问导致证书不匹配
4. **订阅端口必须在CDN支持列表**: 443/2053/2083/2087/2096/8443
5. **CDN IP获取必须用指定DNS**: 222.246.129.80 | 59.51.78.210（湖南电信DNS）
6. **测试必须模拟真实客户端**: 不使用-k/--insecure参数
7. **证书路径**: 从config.py的CERT_DIR读取，禁止硬编码
8. **环境变量**: 从.env文件读取，路径从BASE_DIR拼接
9. **HY2端口跳跃**: 必须UDP+TCP双规则，目标端口与singbox配置的listen_port一致
10. **SOCKS5 AI路由**: 配置AI_SOCKS5_SERVER后自动生效，AI网站走SOCKS5，X/推特/groK排除
11. **跨文件配置一致性**: 修改任何配置必须全局搜索所有引用该配置的文件
