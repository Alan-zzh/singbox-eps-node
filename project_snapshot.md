# 项目状态快照 (Project Snapshot)

## 当前版本
**v1.0.48** (脱敏处理+一键安装脚本+GitHub公开仓库)

---

## 版本历史
| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.0.34 | 2026-04-20 | HTTPS订阅服务+Cloudflare正式证书+端口9443 |
| v1.0.35 | 2026-04-20 | 文档完善+CDN/SOCKS5状态确认+证书申请流程记录 |
| v1.0.36 | 2026-04-20 | CDN优选IP改为实时DNS解析+每小时自动更新 |
| v1.0.37 | 2026-04-20 | 恢复固定优选IP池（中国用户实测低延迟IP） |
| v1.0.38 | 2026-04-20 | 新增sing-box JSON配置接口，内置AI流量自动路由规则 |
| v1.0.39 | 2026-04-20 | 修复Trojan-WS链接缺少insecure=1参数 |
| v1.0.40 | 2026-04-20 | SOCKS5路由规则优化：加入aistudio.google.com，排除X/推特/groK |
| v1.0.41 | 2026-04-20 | 修复Trojan-WS协议不通：添加SSL配置+修复path参数URL编码 |
| v1.0.42 | 2026-04-21 | 修复订阅端口9443不通：防火墙放行9443+默认端口6969→9443+path编码一致性 |
| v1.0.43 | 2026-04-21 | 端口硬编码锁定+防篡改校验+防火墙全放行+健康检查自动恢复+标准操作流程 |
| v1.0.44 | 2026-04-21 | 修复V2rayN订阅更新失败：9443→2087走CDN+域名访问解决证书匹配 |
| v1.0.45 | 2026-04-21 | 全面消除硬编码+DNS优选CDN+HY2规避修复+新VPS适配 |
| v1.0.46 | 2026-04-21 | HY2双协议保障恢复+SOCKS5 AI路由文档补全+铁律10文档同步 |
| v1.0.47 | 2026-04-21 | HY2端口跳跃无感切换：sing-box配置添加hop_ports字段 |
| v1.0.48 | 2026-04-21 | 脱敏处理+一键安装脚本+GitHub仓库公开+临时脚本清理 |

---

## 最新更新内容 (v1.0.48)

### 1. 全面脱敏处理
- 所有代码和文档中的IP地址、域名、密码、Token替换为占位符或从环境变量读取
- 删除26个临时check/deploy/test脚本（含硬编码凭据）
- 创建 .gitignore 排除 .env、cert/、logs/、backups/ 等敏感目录
- 创建 .env.example 作为配置模板

### 2. 一键安装脚本 (install.sh)
- 全自动部署：检测系统→安装依赖→安装Singbox→克隆仓库→生成密码→配置证书→启动服务
- 自动生成UUID/密码/Reality密钥对
- 自动检测服务器公网IP
- 支持Cloudflare API Token自动申请15年证书
- 自动配置HY2端口跳跃iptables规则（UDP+TCP双协议）
- 安装完成后自动验证并输出订阅链接

### 3. GitHub仓库
- 仓库地址：https://github.com/Alan-zzh/singbox-eps-node
- 一键安装命令：`bash <(curl -sL https://raw.githubusercontent.com/Alan-zzh/singbox-eps-node/main/install.sh)`

---

## 最新更新内容 (v1.0.47)

### HY2端口跳跃实现无感切换
**问题**: sing-box JSON配置中缺少 `hop_ports` 字段，客户端不会主动做端口跳跃，只连443
**修复**: subscription_service.py 的sing-box配置中添加 `"hop_ports": "21000-21200"`
**效果**: 
- 客户端初始连接443端口
- 后续QUIC连接自动在21000-21200范围内跳跃
- 服务端iptables将21000-21200全部DNAT到443，无论跳到哪个端口都能到达HY2
- 当某个端口被封锁/干扰时，客户端自动跳到其他端口，**无需断线重连，无感切换**

---

## 最新更新内容 (v1.0.46)

### 1. HY2端口跳跃恢复TCP+UDP双协议保障
**问题**: v1.0.45修复时错误地移除了TCP规则，只保留UDP规则。当UDP被封时HY2完全不可用，无TCP兜底
**根因**: 文档未明确说明必须同时保留TCP和UDP规则，AI凭自己理解做判断，认为"HY2只用UDP"就删了TCP
**修复**: cert_manager.py恢复TCP规则，config.py新增第6条HY2规避说明（双协议保障+历史教训）

### 2. SOCKS5 AI路由规则文档补全
**问题**: SOCKS5 AI路由规则代码已实现但文档未记录，TECHNICAL_DOC.md严重过时
**根因**: 改代码时没有同步更新文档（流程纪律问题）
**修复**: 
- TECHNICAL_DOC.md新增第4节"SOCKS5 AI路由规则"，完整记录AI域名列表、排除规则、触发条件
- subscription_service.py新增SOCKS5路由规则注释（写死的规则，禁止随意修改）
- config.py HY2规避说明标注"必须完整保留，禁止删减"

### 3. 新增铁律10：改代码必须同步更新文档
**问题**: 多次出现"代码改了文档没改"的情况，导致文档过时，下一个AI基于过时文档犯错
**修复**: AI_DEBUG_HISTORY.md新增规则10，强制要求每次改代码必须同步更新三个文档

---

## 最新更新内容 (v1.0.45)

### 1. 全面消除硬编码（域名/IP/端口/凭据/路径）
**问题**: 代码中硬编码了域名、服务器IP、SOCKS5凭据、文件路径等，导致新VPS部署时必须手动修改大量代码

**修复**:
- `config.py`: 新增 `_detect_server_ip()` 自动检测公网IP，新增 `_load_env_value()` 统一读取.env，新增 `get_sub_domain()` 统一获取订阅域名
- `subscription_service.py`: 所有硬编码域名改为从 `get_sub_domain()` 动态读取，SOCKS5凭据改为从环境变量读取，文件路径改为从 `BASE_DIR`/`CERT_DIR` 拼接
- `config_generator.py`: 所有硬编码路径改为从 `config.py` 的 `BASE_DIR`/`CERT_DIR` 读取
- `cert_manager.py`: .env文件路径改为从 `BASE_DIR` 拼接

### 2. CDN优选节点改用指定DNS方案
**问题**: `cdn_monitor.py` 使用固定IP池+随机ping，IP可能过期失效

**修复**: 改为三层获取策略：
1. **指定DNS解析**（222.246.129.80 | 59.51.78.210，湖南电信DNS，返回对中国延迟最低的IP）
2. **降级DNS**（114.114.114.114）
3. **固定IP池降级**（原有PREFERRED_IPS列表）

### 3. HY2规避配置一致性修复
**问题**: 端口跳跃配置三处不一致：
- `cert_manager.py`: 21000-21200 → **4433**（❌ HY2不在4433监听！）
- `subscription_service.py` Base64链接: 22000-22200 → 443（范围不一致）
- `subscription_service.py` sing-box配置: 无mport

**修复**:
- 统一端口跳跃范围为 **21000-21200 → 443**（与singbox配置中HY2的listen_port=443一致）
- `cert_manager.py`: 修复目标端口4433→443，移除TCP规则（HY2只用UDP），清理旧规则
- `subscription_service.py`: mport统一为 `443,21000-21200`
- `config.py`: 新增HY2规避配置说明注释

### 4. 清理临时脚本（26个）
删除根目录下所有临时check/deploy/test脚本，这些脚本包含硬编码IP和密码，存在安全隐患

### 5. SOCKS5凭据消除硬编码
**问题**: `subscription_service.py` 中硬编码了SOCKS5凭据

**修复**: 改为从环境变量 `AI_SOCKS5_SERVER`/`AI_SOCKS5_PORT`/`AI_SOCKS5_USER`/`AI_SOCKS5_PASS` 读取，未配置时不生成SOCKS5节点

---

## 服务器标准操作流程 (SOP)

### 启动前状态检查
```bash
systemctl status singbox singbox-sub singbox-cdn
ss -tlnp | grep -E '443|8443|2053|2083|2087'
iptables -L INPUT -n | head -1
bash /root/singbox-eps-node/scripts/health_check.sh
```

### 故障恢复流程
1. **服务挂了**: 健康检查5分钟内自动重启
2. **手动恢复**: `bash /root/singbox-eps-node/scripts/health_check.sh`
3. **重装恢复**: 
   ```bash
   cd /root/singbox-eps-node
   systemctl restart singbox singbox-sub singbox-cdn
   python3 -c "from scripts.config import save_port_lock; save_port_lock()"
   bash scripts/health_check.sh
   ```

### 新VPS部署流程
1. 克隆代码到 `/root/singbox-eps-node/`
2. 创建 `.env` 文件，填入所有环境变量（SERVER_IP会自动检测）
3. 运行 `python3 scripts/config_generator.py` 生成singbox配置
4. 运行 `python3 scripts/cert_manager.py --cf-cert` 申请证书
5. 运行 `python3 scripts/cert_manager.py --setup-iptables` 设置HY2端口跳跃
6. 启动服务: `systemctl start singbox singbox-sub singbox-cdn`
7. 验证: `bash scripts/health_check.sh`

### 操作日志记录
- 健康检查日志: `/root/singbox-eps-node/logs/health_check.log`
- 订阅服务日志: `journalctl -u singbox-sub`
- singbox主服务日志: `journalctl -u singbox`

---

## 当前服务状态
- **singbox**: active (端口443/8443/2053/2083)
- **singbox-sub**: active (HTTPS://0.0.0.0:2087，走CDN)
- **singbox-cdn**: active (每小时指定DNS解析更新优选IP)
- **iptables**: INPUT默认ACCEPT（全放行）
- **acme.sh**: 自动续期已配置 (每天8:48)
- **健康检查**: 每5分钟自动执行

## 订阅链接
- **域名（推荐，走CDN）**: https://{CF_DOMAIN}:2087/sub/JP
- **sing-box JSON**: https://{CF_DOMAIN}:2087/singbox/JP
- **证书**: Let's Encrypt正式证书（通配符域名），域名访问自动匹配
- ⚠️ **禁止用IP访问**: IP访问会导致SSL证书域名不匹配
- ⚠️ **CF_DOMAIN从.env动态读取**: 不再硬编码域名

## 节点列表（5-6个，取决于SOCKS5是否配置）
1. ePS-JP-VLESS-Reality: {SERVER_IP}:443 (直连)
2. ePS-JP-VLESS-WS-CDN: 优选IP:8443 (CDN，每小时DNS解析更新)
3. ePS-JP-VLESS-HTTPUpgrade-CDN: 优选IP:2053 (CDN，每小时DNS解析更新)
4. ePS-JP-Trojan-WS-CDN: 优选IP:2083 (CDN，每小时DNS解析更新)
5. ePS-JP-Hysteria2: {SERVER_IP}:443 (直连，端口跳跃21000-21200→443，UDP+TCP)
6. AI-SOCKS5: {AI_SOCKS5_SERVER}:{AI_SOCKS5_PORT} (外部代理，可选)

## 核心目录
```
/root/singbox-eps-node/
├── .env                    # 环境变量（所有配置集中管理）
├── config.json             # singbox配置文件
├── cert/                   # SSL证书（Let's Encrypt，通配符域名）
│   ├── cert.pem
│   ├── key.pem
│   └── fullchain.pem
├── data/
│   ├── singbox.db          # SQLite数据库（CDN IP等）
│   └── .port_lock          # 端口锁定文件（防篡改）
├── scripts/
│   ├── config.py           # 全局配置（v1.0.4，自动检测IP+统一读取.env）
│   ├── logger.py           # 日志管理
│   ├── cdn_monitor.py      # CDN监控脚本（v1.0.5，指定DNS解析+降级方案）
│   ├── subscription_service.py  # 订阅服务（v1.0.39+，消除硬编码）
│   ├── config_generator.py # 配置生成器（v1.0.19，消除硬编码路径）
│   ├── cert_manager.py     # 证书管理（v1.0.4+，修复HY2端口跳跃）
│   ├── tg_bot.py           # Telegram机器人
│   └── health_check.sh     # 健康检查与自动恢复（每5分钟）
├── logs/
│   └── health_check.log    # 健康检查日志
└── backups/                # 备份目录
```

## 端口分配表
| 端口 | 服务 | CDN支持 | 用途 |
|------|------|---------|------|
| 443 | singbox | ✅ | VLESS-Reality + Hysteria2 |
| 2053 | singbox | ✅ | VLESS-HTTPUpgrade |
| 2083 | singbox | ✅ | Trojan-WS |
| 2087 | singbox-sub | ✅ | 订阅服务（走CDN） |
| 8443 | singbox | ✅ | VLESS-WS |
| 1080 | singbox | ❌ | SOCKS5本地代理 |
| 21000-21200 | iptables→443 | ❌ | Hysteria2端口跳跃（UDP+TCP双协议保障） |

## .env 必需变量清单
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
AI_SOCKS5_SERVER=   # AI SOCKS5服务器（可选）
AI_SOCKS5_PORT=     # AI SOCKS5端口（可选）
AI_SOCKS5_USER=     # AI SOCKS5用户名（可选）
AI_SOCKS5_PASS=     # AI SOCKS5密码（可选）
COUNTRY_CODE=JP     # 国家代码
SUB_TOKEN=          # 订阅Token（可选）
```

## 踩坑记录
1. **端口冲突**: 8443被singbox主服务占用，订阅服务不能使用
2. **SSL配置**: Flask的ssl_context需要fullchain.pem和key.pem
3. **⚠️ IP访问HTTPS=证书不匹配**: SSL证书颁发给域名，用IP访问时证书域名不匹配，V2rayN等客户端拒绝连接。必须使用域名访问
4. **⚠️ CDN端口限制**: Cloudflare CDN只代理 443/2053/2083/2087/2096/8443，其他端口CDN不转发
5. **⚠️ 默认端口陷阱**: v1.0.42前默认端口6969导致防火墙不匹配，已硬编码解决
6. **⚠️ 测试必须不跳过验证**: curl -k测试通过不代表V2rayN能通，必须模拟真实客户端的证书验证
7. **⚠️ HY2端口跳跃目标必须与listen_port一致**: v1.0.45前cert_manager.py转发到4433，但HY2监听443，导致端口跳跃无效
8. **⚠️ CDN IP获取必须用指定DNS**: 222.246.129.80 | 59.51.78.210（湖南电信DNS），日本服务器DNS返回的IP对中国延迟高
9. **⚠️ 禁止硬编码凭据**: SOCKS5等凭据必须从.env读取，禁止在代码中硬编码
10. **⚠️ HY2端口跳跃必须UDP+TCP双规则**: UDP是核心(QUIC)，TCP是降级兜底，禁止只设一种
11. **⚠️ 改代码必须同步更新文档**: 代码改了文档没改=文档过时=下一个AI犯错

## 下一步待办
- [ ] 部署v1.0.45到服务器并验证所有功能
- [ ] 修复服务器上HY2端口跳跃iptables规则（4433→443）
- [ ] 开发SOCKS5自动切换功能（需要更多节点）
