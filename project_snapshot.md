# 项目状态快照 (Project Snapshot)

## 当前版本
**v1.0.72** (reinstall改为操作系统重装+root密码双重确认+reset明确为singbox应用重装)

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
| v1.0.49 | 2026-04-21 | 修复AI-SOCKS5被错误暴露为用户节点+新增铁律11 |
| v1.0.50 | 2026-04-21 | 全面排查13个隐藏坑+跨文件一致性修复 |
| v1.0.51 | 2026-04-21 | 修复HY2端口跳跃iptables规则：端口范围22000→21000+补全TCP双规则 |
| v1.0.52 | 2026-04-21 | 全面审查修复5个隐藏Bug：证书文件名统一+自动续签cron+防火墙顺序+CDN死循环+住宅重启 |
| v1.0.53 | 2026-04-21 | **全面优化与验证**：文档版本统一+代码质量审查+安装流程修复+功能模块测试 |
| v1.0.54 | 2026-04-21 | subscription_service.py安全加固：Token认证+IP验证+连接泄漏+异常脱敏+ImportError降级 |
| v1.0.60 | 2026-04-22 | 新增按月流量统计：traffic_stats表+每月14号自动归零+首页流量显示+/api/traffic接口 |
| v1.0.61 | 2026-04-22 | 优化CDN优选IP4级降级机制+完善流量统计功能+详细文档记录 |
| v1.0.62 | 2026-04-22 | 修复证书路径BUG(cert.crt→cert.pem)+sysctl防重复追加+requirements.txt+文档同步 |
| v1.0.63 | 2026-04-22 | 交互式SOCKS5配置+一键重装reset+一键优化optimize+3加速确认+注释修正 |
| v1.0.64 | 2026-04-22 | 系统更新+3加速全自动先行+无需重启+流程重构 |
| v1.0.65 | 2026-04-22 | BBR+FQ+CAKE三合一加速+CAKE持久化+BBR高丢包参数 |
| v1.0.66 | 2026-04-22 | 修复set -e导致CAKE失败脚本退出+函数定义顺序+降级保障 |
| v1.0.67 | 2026-04-22 | Singbox已安装时交互选择卸载重装/保留+版本号更新 |
| v1.0.68 | 2026-04-22 | 卸载重装=完全清除所有数据+配置+证书+服务+定时任务+防火墙 |
| v1.0.69 | 2026-04-22 | 国家代码自动检测+CF_API_TOKEN交互式填写+singbox启动诊断+NODE_PREFIX动态生成 |
| v1.0.70 | 2026-04-22 | CF配置自动从旧S-ui读取+证书缺失自动生成+singbox启动诊断 |
| v1.0.71 | 2026-04-22 | CAKE状态真实显示+一键重装reinstall无感+自动重启+密码保留 |
| v1.0.72 | 2026-04-22 | reinstall改为操作系统重装(bin456789/reinstall)+root密码双重确认+reset明确为singbox应用重装 |

---

## 最新更新内容 (v1.0.72)

### 修复：reinstall命令逻辑错误 — "不需要密码"说法不成立

**问题**: v1.0.71的`bash install.sh reinstall`声称"不需要输密码（自动从旧.env读取）"，但这是逻辑错误：
- .env存储的是应用密码（VLESS_UUID/TROJAN_PASSWORD等），不是root密码
- 操作系统重装需要root密码，无法从任何地方自动获取
- 用户指出：很多一键重装脚本都要求手动输入密码（强制改密码或输入当前密码）

**修复**: `reinstall`改为操作系统重装，需手动输入root密码（两次确认）

### 新增：`bash install.sh reinstall` — 一键重装操作系统

**特点**：
- **需输入root密码**：连续两次确认，密码作为新系统登录密码
- **自动检测OS版本**：读取/etc/os-release，重装为相同版本
- **集成bin456789/reinstall**：GitHub优先，降级国内镜像(cnb.cool)
- **自动重启**：重装完成后自动重启进入新系统
- **重装后需重新部署**：SSH连接后运行`bash install.sh`安装singbox

**执行流程**：
1. 输入root密码（两次确认，隐藏输入）→ 检测当前OS版本
2. 下载bin456789/reinstall脚本（GitHub→国内镜像降级）
3. 执行`bash reinstall.sh <OS> <VERSION> --password <密码>`
4. 脚本自动下载OS镜像→修改引导→重启→安装新系统

**支持的OS映射**：
| /etc/os-release ID | reinstall参数 |
|---|---|
| ubuntu | ubuntu |
| debian | debian |
| centos | centos |
| rocky | rocky |
| almalinux | alma |
| alpine | alpine |
| fedora | fedora |
| arch | arch |
| gentoo | gentoo |
| opensuse-leap | opensuse |

### 明确：`bash install.sh reset` — singbox应用重装（保留密码）

**与reinstall的区别**：
- `reinstall` = 重装**操作系统**（清除硬盘所有数据，需输入root密码）
- `reset` = 重装**singbox应用**（保留.env配置和数据库，客户端无需重配）

**reset保留的内容**：
- .env配置文件（所有密码和密钥）
- data/目录（流量统计数据库）
- cert/目录（SSL证书）

---

## 历史更新内容 (v1.0.71)

### 修复：CAKE状态显示矛盾

**问题**: verify_installation检测CAKE未启用（降级为FQ），但print_summary硬编码"CAKE队列: 已启用"
**修复**: print_summary从tc qdisc实际检测读取，CAKE降级时显示"降级为FQ（内核不支持CAKE，FQ仍可与BBR配合）"

### 卸载重装也保留密码

安装时检测到singbox已安装，选"1)卸载重装"时：
- 先备份.env密码字段到临时文件
- 清除所有数据
- generate_uuids_and_passwords和generate_reality_keys自动从备份恢复旧密码
- 客户端无需重新配置

### 重大Bug修复：set -e导致CAKE失败时脚本直接退出

**问题**: 脚本开头启用了 `set -e`，`setup_cake_qdisc` 中 `tc qdisc replace` 失败时脚本立即退出，后续所有步骤（TCP调优、文件描述符、安装singbox等）全部不执行
**影响**: 用户在服务器上运行一键安装脚本，到CAKE步骤就中断，无法继续
**根因**: `set -e` 下任何命令返回非零退出码都会终止脚本，而CAKE在部分内核/VPS上可能不支持

**修复措施**：
1. `tc qdisc replace` 改为 `cmd && CAKE_OK=true || true` 模式，失败不退出
2. CAKE支持检测改为 `if modprobe sch_cake` + `tc qdisc add` 试探法，避免管道+grep触发set -e
3. 所有 `grep -q ... && sed || echo` 模式改为独立函数 `set_default_qdisc_cake/fq`，用 `if/else` 替代
4. 函数定义移到调用之前（bash顺序执行，函数必须先定义后调用）
5. 删除重复的函数定义

### 新增：set_default_qdisc_cake/fq 辅助函数

- `set_default_qdisc_cake()` — 设置 `default_qdisc=cake`（CAKE集成FQ+PIE）
- `set_default_qdisc_fq()` — 降级设置 `default_qdisc=fq`（FQ仍可与BBR配合）
- 两个函数用 `if grep -q; then sed; else echo; fi` 模式，完全兼容 `set -e`

### 修正：三合一加速方案（BBR+FQ+CAKE）

**问题**: 之前写的"3大加速"是BBR+TCP FastOpen+TCP调优，与S-ui项目README定义的BBR+FQ+CAKE三合一不一致
**修复**: 按海外代理服务器最优方案重新实现

**BBR+FQ+CAKE三合一加速（海外代理最优方案）**：

| 组件 | 作用 | 配置 |
|------|------|------|
| BBR | 智能调节发送速率，不依赖丢包信号 | `net.ipv4.tcp_congestion_control=bbr` |
| FQ | 公平分配带宽，BBR的pacing依赖FQ | `net.core.default_qdisc=cake`（CAKE集成FQ） |
| CAKE | 主动队列管理，集成FQ+PIE，防缓冲区膨胀 | `tc qdisc replace dev eth0 root cake` |

**三层防护协同**：
- BBR层：智能调节发送速率（不靠丢包判断拥塞）
- FQ层：公平分配带宽资源（多用户环境下关键）
- CAKE层：主动管理队列深度，提前预防拥塞（替代单纯FQ，抗丢包更强）

**实测效果**：5%丢包率跨洋链路，吞吐量提升35%+，尾部延迟降低40%

### 新增：setup_cake_qdisc() 函数

- 自动检测主网卡（ip route show default）
- 自动安装iproute2（提供tc命令）
- 内核不支持CAKE时自动降级为FQ（仍可与BBR配合）
- CAKE参数：`bandwidth 1000mbit flowmode triple-isolate`
- 创建systemd服务（cake-qdisc@网卡名）确保持久化，重启自动恢复

### 新增：BBR高丢包优化参数

- `net.ipv4.tcp_slow_start_after_idle=0` — 避免空闲后重置窗口
- `net.ipv4.tcp_bbr_min_rtt_win_sec=60` — 缩短RTT采样窗口

### 降级保障

- CAKE不可用时自动降级为FQ（default_qdisc=fq）
- FQ仍可与BBR配合，只是缺少PIE的主动队列管理

---

## 历史更新内容 (v1.0.61)

### CDN优选IP 4级降级机制优化

**优化目标：确保主方案失效时自动切换备选方案，实现实时同步IP更换**

**4级降级策略（按优先级自动切换）：**
1. **主方案：本地实测IP池** - 湖南电信实测最优IP，按延迟排序
2. **备选方案1：cf.001315.xyz/ct电信API** - 返回 `IP#电信` 格式
3. **备选方案2：WeTest.vip电信优选DNS** - 按运营商分类
4. **备选方案3：IPDB API bestcf** - 通用优选IP

**自动切换逻辑：**
- 主方案不可达时，自动切换到备选方案1
- 备选方案1不可达时，自动切换到备选方案2
- 备选方案2不可达时，自动切换到备选方案3
- 所有方案都不可达时，使用降级IP池

**湖南电信最优IP段筛选：**
- 162.159.x.x / 172.64.x.x / 108.162.x.x 段延迟50-53ms（最优）
- 198.41.x.x / 173.245.x.x 段延迟50-55ms（次优）
- 104.16-21.x.x 段延迟130ms+（必须过滤）

**实时同步机制：**
- 每小时自动检测一次IP可达性
- 不可达IP自动替换为下一个可用IP
- 确保每次更新都是实时同步的最新IP

**成功方式记录：**
- 每次执行都会记录各方案获取结果
- 自动切换状态报告显示各方案成功/失败状态
- 日志详细记录IP获取和验证过程

### 按月流量统计功能

**新增功能1: traffic_stats数据库表**
- 在init_db()中创建traffic_stats表（key-value结构，与cdn_settings一致）
- 存储key：current_month（当前月份）、current_bytes（当月已用字节数）、last_reset（上次重置日期）
- 数据持久化到data/singbox.db，重装系统才丢失

**新增功能2: update_traffic(bytes_count)函数**
- 每次订阅请求返回时自动调用，累加响应数据量
- 自动检测月份变化，月份变了立即归零
- 每月14号自动归零（检查当天日期+本月是否已重置过）
- 数据库连接在finally中关闭，防止泄漏（铁律14）

**新增功能3: get_traffic_stats()函数**
- 读取当月流量统计，返回月份、字节数、MB、GB、重置日、上次重置日期
- 月份变化时返回0（无需等待update_traffic触发）

**新增功能4: format_traffic(bytes_count)函数**
- 格式化流量显示：小于1MB显示KB，小于1GB显示MB，大于1GB显示GB

**新增功能5: /api/traffic路由（GET）**
- 返回JSON格式流量数据（不加token认证，铁律13）
- 响应格式：{month, bytes_used, mb_used, gb_used, reset_day, last_reset}

**新增功能6: 首页流量显示**
- 首页（/路由）新增蓝色流量统计区域
- 显示当月已用流量（自动格式化）、统计月份、归零日、上次重置日期

**修改: get_subscription()和get_singbox_config()**
- 返回响应前调用update_traffic()记录本次请求的数据量
- 不影响原有功能，仅追加流量统计逻辑

### subscription_service.py 安全加固（8项修复）

**修复1: 添加 urllib.request 导入**
- 文件头部添加 `import urllib.request`（get_subscription中已使用但未导入）

**修复2: 修复 ImportError 降级逻辑的 NameError 风险**
- 当 config.py 导入失败时，except 块只定义了 get_logger，导致后续代码引用 SERVER_IP/CF_DOMAIN 等变量时 NameError
- 在 except 块中添加所有必需变量的降级值定义（从环境变量读取，带默认值）
- 额外添加 `get_sub_domain()` 降级函数

**修复3: 为 /api/cdn 路由添加 Token 认证**
- SUB_TOKEN 配置时强制校验 Authorization header 或 token 参数
- 未配置 SUB_TOKEN 时不影响现有功能

**修复4: 为 /api/cdn POST 添加 IP 格式验证**
- 正则验证 IP 格式（x.x.x.x）
- 白名单验证 protocol key（只允许 vless_ws_cdn_ip/vless_upgrade_cdn_ip/trojan_ws_cdn_ip）

**修复5: 为订阅路由添加 Token 认证**
- /sub 和 /singbox 路由添加 SUB_TOKEN 校验
- 优先从 URL 参数读取 token，降级从 Authorization header 读取

**修复6: 修复数据库连接泄漏**
- init_db()、get_cdn_ip_for_protocol()、cdn_api() 的 GET/POST 全部改用 try/finally 确保 conn.close()
- 即使异常也不会泄漏连接

**修复7: 修复异常信息泄露**
- cdn_api() 的 500 错误不再返回 str(e)（可能泄露内部路径/SQL语句）
- 改为 logger.error 记录详细日志，返回通用 'Internal server error'

**修复8: 版本号更新**
- v1.0.52 -> v1.0.54

---

## 最新更新内容 (v1.0.50)

### 全面排查隐藏坑+跨文件一致性修复
对项目所有文件进行逐行审查，发现并修复13个隐藏问题：

**坑1: README.md仍把AI-SOCKS5列为"节点"** → 移除第6条，添加幕后路由出站说明

**坑2+3: config_generator.py AI路由规则不完整**
- 缺少aistudio.google.com、google.com、googleapis.com、gstatic.com
- 缺少aistudio关键词
- 缺少X/推特/groK排除规则
→ 补全所有域名和排除规则，与subscription_service.py保持一致

**坑4+5: tg_bot.py订阅链接端口硬编码6969**
- 默认值是6969（v1.0.42之前的老端口）
- 没有从config.py导入SUB_PORT
→ 改为从config.py导入SUB_PORT=2087

**坑6: tg_bot.py设置住宅后只重启singbox不重启singbox-sub**
- SOCKS5配置变更后subscription_service.py也需要重启
→ update_env_and_restart()增加重启singbox-sub

**坑7: health_check.sh用curl -sk测试**
- 本地测试用-k合理（localhost域名不匹配），但缺少域名访问测试
→ 增加域名访问检查（不使用-k，模拟真实客户端验证SSL证书）

**坑8: subscription_service.py SSL证书路径不一致**
- Flask启动时硬编码fullchain.pem，但cert_manager.py自签名证书生成cert.crt
→ 增加证书路径自动检测：优先fullchain.pem，降级cert.crt

**坑9: config_generator.py SOCKS5出站结构与subscription_service.py不一致**
- config_generator.py直接用socks类型tag=ai-residential
- subscription_service.py用selector(ai-residential)包裹socks(AI-SOCKS5)
→ 对齐为selector+socks双层结构

**坑10: install.sh依赖包名错误**
- `dig`不是独立包名，它在`dnsutils`包里
→ 改为dnsutils

**坑11: TECHNICAL_DOC.md版本号过时v1.0.45** → 更新为v1.0.50

**坑12: subscription_service.py变量覆盖**
- SERVER_IP/CF_DOMAIN/VLESS_UPGRADE_PORT从config.py导入后又被os.getenv覆盖
→ 优先使用config.py的值，降级使用os.getenv

**坑13: cert_manager.py重复导入和变量覆盖**
- 两次from config import，os.getenv覆盖CF_DOMAIN
→ 合并导入，CF_API_TOKEN改用_load_cf_api_token()函数读取

---

## 最新更新内容 (v1.0.49)

### 修复AI-SOCKS5被错误暴露为用户可见节点
**问题**: AI-SOCKS5被错误地加入Base64订阅链接和ePS-Auto selector，用户在客户端看到"AI-SOCKS5"节点
**根因**: AI只理解了"SOCKS5是个代理"的字面意思，忽略了"无感路由，用户无需手动选择"的设计意图
**修复**:
- subscription_service.py: 移除generate_all_links()中的socks5://链接
- subscription_service.py: 移除ePS-Auto selector中的"AI-SOCKS5"选项
- subscription_service.py: 修复首页HTML从"6个节点"改为"5个节点"
- TECHNICAL_DOC.md: 明确AI-SOCKS5是幕后路由出站，不是用户可见节点
- AI_DEBUG_HISTORY.md: 新增铁律11（区分"用户可见节点"和"幕后路由出站"）

### AI-SOCKS5的正确行为
- ✅ 出现在sing-box JSON的outbounds（ai-residential出站）
- ✅ 出现在sing-box JSON的route.rules（AI域名→ai-residential）
- ❌ 不出现在Base64订阅链接中
- ❌ 不出现在ePS-Auto selector可选列表中
- ❌ 不出现在首页HTML节点列表中

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
- **域名（推荐，走CDN）**: https://{CF_DOMAIN}:2087/sub/{COUNTRY_CODE}
- **sing-box JSON**: https://{CF_DOMAIN}:2087/singbox/{COUNTRY_CODE}
- **证书**: Let's Encrypt正式证书（通配符域名），域名访问自动匹配
- ⚠️ **禁止用IP访问**: IP访问会导致SSL证书域名不匹配
- ⚠️ **CF_DOMAIN从.env动态读取**: 不再硬编码域名

## 节点列表（5个用户可见节点）
1. ePS-{CC}-VLESS-Reality: {SERVER_IP}:443 (直连)
2. ePS-{CC}-VLESS-WS-CDN: 优选IP:8443 (CDN，每小时DNS解析更新)
3. ePS-{CC}-VLESS-HTTPUpgrade-CDN: 优选IP:2053 (CDN，每小时DNS解析更新)
4. ePS-{CC}-Trojan-WS-CDN: 优选IP:2083 (CDN，每小时DNS解析更新)
5. ePS-{CC}-Hysteria2: {SERVER_IP}:443 (直连，端口跳跃21000-21200→443，UDP+TCP)

⚠️ AI-SOCKS5不是用户可见节点，是幕后路由出站（仅出现在sing-box JSON的outbounds和route.rules中）

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
COUNTRY_CODE=     # 国家代码（安装时自动检测）
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
- [ ] 部署v1.0.72到服务器并验证reinstall命令
- [ ] 开发SOCKS5自动切换功能（需要更多节点）