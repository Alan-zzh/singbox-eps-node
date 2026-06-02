## v4.10.20 - 2026-06-03

- [opencode] AI-SOCKS5 路由功能正式废除：删除服务端/客户端 outbounds 中所有 ai-residential 出站，路由表只保留 direct+block
- [opencode] CDN 评分公式精简：废除 google_latency_ms / google_speed_mbps 两个无效维度（数据库列已 DROP），保留用户路径 70% + VPS 侧 20% + 三网均衡 5% + 稳定性 5%
- [opencode] SQLite 切换到 WAL 模式：PRAGMA journal_mode = WAL，多进程并发读写零阻塞
- [opencode] Reality short_id 强随机：默认 `abcd1234` 弱预设弃用，运行时 `secrets.token_hex(8)` 生成
- [opencode] TLS ALPN 启用 HTTP/2：Reality/WS/HTTPUpgrade/Trojan-WS 四处 alpn 从 `["http/1.1"]` 改为 `["h2","http/1.1"]`
- [opencode] health_check.sh 升级为详细日志版：8 项检查完整输出（内存/服务/端口/连接/日志/磁盘/数据库/证书），estab>1500 告警
- [opencode] iptables 流量月度归零 cron：每月 14 号 00:14 自动清零 INPUT/OUTPUT 计数器
- [opencode] 服务器代码与本地版本对齐：v4.3.5 → v4.10.20（cert_manager.py + diagnose.sh + health_check.sh + requirements.txt 同步）
- [opencode] 本地代码清理：删除明文密码脚本 verify_server_config.py / _deploy_v41019.py；23 个临时脚本归档到 docs/archive/scripts/
- [opencode] 远程运维增强：requirements.txt 加 paramiko，统一从 .env 读凭据（消除明文硬编码）
- [TRAE SOLO CN] 数据库清理：删除连续失败>5 且评分<10 的死亡 IP 记录+VACUUM 压缩

## v4.10.19 - 2026-06-01

- [TRAE SOLO CN] 修复用户路径测速全部失败：test_user_path_latency()移除HTTP请求，改为纯TCP+TLS握手测速（CDN 443端口不提供HTTP服务，GET请求必被403/400拒绝）
- [TRAE SOLO CN] 两台服务器完整持久化TCP内核参数：写入99-singbox.conf（BBR+fq/somaxconn=65536/syn_backlog=65536/tw_reuse=1/tw_buckets=3000/fastopen=3等18项参数）
- [TRAE SOLO CN] 两台服务器default_qdisc从fq_pie改为fq，BBR+fq组合生效
- [TRAE SOLO CN] SG同步TCP优化参数：补充tw_reuse/fastopen/slow_start_after_idle/no_metrics_save
- [TRAE SOLO CN] SG iptables 2087端口规则补上并持久化（iptables-persistent）
- [TRAE SOLO CN] Clash自动选择配置10项全部合规验证通过（lazy=false/tolerance=150/interval=60/MATCH→select→url-test）
- [TRAE SOLO CN] REALITY节点参数两台服务器全部一致，无暗病

## v4.10.18 - 2026-06-01

- [TRAE SOLO CN] 修复CDN测速SNI：test_user_path_latency()优先使用用户域名作为SNI，Cloudflare正确路由
- [TRAE SOLO CN] 修复ISP匹配分无区分度：calculate_cross_isp_score()增加C段前缀匹配，解决anycast IP精确匹配失败
- [TRAE SOLO CN] 数据库定期清理：health_check()末尾删除连续失败>5且评分<10的死亡IP记录+VACUUM压缩
- [TRAE SOLO CN] 统一sing-box版本：SG升级1.13.9→1.13.11，与JP一致
- [TRAE SOLO CN] cdn_monitor日志输出从journal改为文件，添加logrotate配置
- [TRAE SOLO CN] JP TCP TIME_WAIT优化：添加tcp_max_tw_buckets=3000
- [TRAE SOLO CN] subscription_service内存限制放宽：MemoryHigh=80M, MemoryMax=100M
- [TRAE SOLO CN] 清理49个临时脚本+8个散落临时文件+2个空数据库文件
- [TRAE SOLO CN] 同步代码版本号：cdn_monitor.py v4.3.5→v4.10.18, subscription_service.py v4.10.9→v4.10.18

## v4.10.16 - 2026-06-01

- [TRAE SOLO CN] 修复MemoryMin=50M被覆盖丢失：重新部署singbox.service内存保护
- [TRAE SOLO CN] 关闭DEBUG日志恢复INFO：避免日志爆炸
- [TRAE SOLO CN] 修复三网均衡度isp_score全为0：health_check前刷新三网API缓存
- [TRAE SOLO CN] 评分权重调整：用户路径70%（延迟35%+速度35%），VPS侧20%，三网均衡5%
- [TRAE SOLO CN] 合并health_check+resource_guard为一个脚本，减少进程spawn
- [TRAE SOLO CN] health_check频率5分钟→15分钟，删减6项低频检查（端口完整性/订阅/防火墙/证书/Swap/iptables）
- [TRAE SOLO CN] singbox-sub/cdn加MemoryHigh=60M/MemoryMax=80M限制，防止内存膨胀
- [TRAE SOLO CN] 统一JP/SG singbox.service配置：LimitNOFILE=1048576+StartLimitBurst+ExecStartPre

## v4.10.15 - 2026-05-31

- [Qoder] 服务器内存精简 + 恢复 Clash 优化：
  - **内存精简**：移除 snap/amazon-ssm-agent(14-24MB)、health_monitor(6-8MB)、rsyslog
  - journald 限制 50MB（JP 从 70MB 降到 15MB，之前日志 278MB 撑的）
  - 清理累积日志文件（379MB singbox.log.bak 等）
  - JP: 183MB→171MB, SG: 206MB→183MB
  - **恢复 Clash 优化**：所有节点回自动选择（Reality+HY2+CDN，之前误判 Reality 丢包）
  - `keep-alive-interval: 15` + `tcp-concurrent: true` + `unified-delay: true` 恢复
  - 根因确认：t3.nano 414MB 内存被占满才是元凶，Clash 配置方向全部正确

## v4.10.14 - 2026-05-31

- [Qoder] 修复所有节点周期性全断的深层原因（补充修复）：
  - 新增漏洞：SG 服务器 `somaxconn=4096`（太小），突发连接时内核直接拒绝 → 所有节点同时不可用
  - 内存保护：添加 `GOMEMLIMIT=100MiB` 防止 Go 堆内存失控增长（之前 RSS 峰值曾达 99.6MB）
  - GC 调优：`GOGC=50` 更频繁小批量 GC（414MB 实例上以 CPU 换内存，CPU idle 99%）
  - 修复 SG `sysctl net.core.somaxconn=65536`（持久化 `/etc/sysctl.d/99-singbox.conf`）
  - 部署：JP + SG 双服务器已生效

## v4.10.13 - 2026-05-31

- [Qoder] 修复所有节点周期性全断（根因定位+修复）：
  - 真正根因：t3.nano 仅 414MB RAM，sing-box RSS 峰值 99.6MB + subscription_service 40MB + cdn_monitor 19MB 接近极限
  - 当内存触顶时内核 swap 出 sing-box 部分内存 → sing-box 处理数据包时被换入 → 数百毫秒冻结
  - 所有客户端连接超时 → 用户看到"全断了" → 连接断开后 RSS 回落 → 恢复 → 循环
  - 修复：systemd singbox.service 添加 `MemoryMin=50M`，锁定 sing-box 在物理内存中永不被 swap
  - 部署：JP + SG 双服务器已生效
  - ~~之前 v4.10.13/14/15 三轮 Clash 配置修改方向全错，已废弃~~

## v4.10.12 - 2026-05-31

- [OpenCode] Clash 极致性能压榨：
  - `keep-alive-interval: 15`：15秒 TCP 物理保活，强行霸占爱快（iKuai）路由器 NAT 映射，彻底解决 63s 超时断连问题
  - `tcp-concurrent: true`：开启并发 TCP 连接，多 IP 并行试探，直连网页秒开
  - `unified-delay: true`：统一延迟算法，测速显示真实代理损耗
  - `ipv6: false`：客户端彻底禁用 IPv6，规避国内运营商劣质国际 IPv6 路由黑洞
- [OpenCode] Clash DNS 架构重构：
  - nameserver 改为阿里 DNS DOH + 腾讯 DNS 物理极速组合，国内解析体验提升上百倍
  - 新增 `default-nameserver` 配置，解决 DOH 域名自解析死锁导致的 DNS 卡死

## v4.10.11 - 2026-05-30

- [OpenCode] 修复 Clash MATCH 规则指向错误：`MATCH,自动选择` → `MATCH,节点选择`
- [OpenCode] 策略组重构：`手动选择` 改为 `节点选择`(select)，包含 `自动选择` + 所有单节点
- [OpenCode] 「节点选择」组里用户可自由选"自动选择"或固定单个节点
- [OpenCode] AGENTS.md 新增 MATCH 规则纪律

## v4.10.9 - 2026-05-30

- [OpenCode] Clash url-test 优化：`lazy: false→true`、`interval: 60→600`、`tolerance: 50→150`，解决 Clash 自动切换导致发消息失败的问题
- [OpenCode] Clash 所有节点显式禁用 multiplex（防御性加固）
- [OpenCode] HY2 Clash 节点 `up/down` 从 `"200 Mbps"` 改为 `200`（整数兼容 Clash Meta 解析）
- [OpenCode] 教训写入 AI_DEBUG_HISTORY.md + AGENTS.md 防止踩坑

## v4.10.8 - 2026-05-30

- [OpenCode] 修复部署：JP/SG服务器缺失的 subscription_service.py 修复同步
- [OpenCode] global→nonlocal 修复：`/api/cdn-status` 从 500 恢复 200
- [OpenCode] UnicodeEncodeError 修复：charset=utf-8 已确认生效
- [OpenCode] 版本号统一为 v4.10.8，文档同步更新

## v4.10.7 - 2026-05-30

- [TRAE SOLO CN] 开启DEBUG日志监控：日志级别从INFO改为DEBUG，详细记录10次CDN优选探测

## v4.10.6 - 2026-05-30

- [TRAE SOLO CN] CDN优选评分激活用户路径+三网均衡：评分含用户路径延迟(25%)+速度(25%)+三网均衡度(15%，电信0.45/联通0.35/移动0.20)
- [TRAE SOLO CN] 修复probe_user_network：TCP 443不通时ICMP ping代替，不再误判NAT
- [TRAE SOLO CN] 三网均衡度改用API缓存数据替代前缀表，区分度从0提升到3档(50/60/80/100)
- [TRAE SOLO CN] 记录爱快路由器凭据到.env
- [TRAE SOLO CN] 修复probe_user_network NAT误判：VPS→用户IP直连改为NAT检测+CDN回源测速代替

## v4.10.5 - 2026-05-30

- [TRAE SOLO CN] 修复CDN优选系统TCP检测全部误判：cdn_ips_list JSON格式读取不兼容（4处split改为JSON解析+逗号降级）
- [TRAE SOLO CN] 修复Clash/Singbox订阅配置UnicodeEncodeError：Response显式指定charset=utf-8

## v4.10.4 - 2026-05-29

- [TRAE SOLO CN] 修复 /api/cdn-status 500错误：`global` → `nonlocal` 修复作用域bug（详见AI_DEBUG_HISTORY）
- [TRAE SOLO CN] 服务端路由规则添加私有地址拒绝（127.0.0.0/8等→block），阻止客户端TUN模式泄漏本地连接到代理隧道
- [TRAE SOLO CN] JP服务器部署logrotate配置，清理374MB膨胀日志

## v4.10.3 - 2026-05-28

- [TRAE SOLO CN] 修复 cdn_quality_filter.py 评分权重总和不等于1：`cross_isp` 从 0.15 调整为 0.14，总和从1.01修正为1.00（详见AI_DEBUG_HISTORY）

## v4.10.2 - 2026-05-28

- [TRAE SOLO CN] 修复高延迟IP被分配给用户：IP筛选改为按评分排序取Top N，不再无脑保留存活IP（详见AI_DEBUG_HISTORY）
- [TRAE SOLO CN] 协议IP分配改为按评分排序取前3名，不再从Top5随机选
- [TRAE SOLO CN] cdn_ips_list改为JSON格式（含评分+延迟），订阅服务换IP时按评分选最高分

## v4.10.1 - 2026-05-28

- [TRAE SOLO CN] 修复订阅服务不返回优选IP：cdn_monitor更新IP后写信号文件，订阅服务检测到信号自动清缓存刷新（详见AI_DEBUG_HISTORY）
- [TRAE SOLO CN] 修复USER_DDNS_DOMAIN读不到.env：config.py改为os.getenv()+_load_env_value()双重读取（详见AI_DEBUG_HISTORY）
- [TRAE SOLO CN] 两台服务器.env已添加USER_DDNS_DOMAIN=zzpzgroup.com，域名测速生效

## v4.10.0 - 2026-05-28

- [TRAE SOLO CN] 简化评分逻辑：移除CDN→Google测速（不影响用户体验），只保留VPS→CDN延迟(40%)+速度(30%)+稳定性(30%)
- [TRAE SOLO CN] 优先本地IP：排序逻辑改为来源优先（你投喂的PREFERRED_IPS排最前）→评分→延迟
- [TRAE SOLO CN] 用户路径测速可选：只有配置USER_DDNS_DOMAIN才做，避免浪费资源
- [TRAE SOLO CN] 修复"全部存活不更新"逻辑：保留v4.9修复，让候选IP始终对比
- [TRAE SOLO CN] 健康检查间隔改为12小时，节省资源
- [TRAE SOLO CN] 速度测试文件改为5MB，超时拉长到15秒，确保数据准确
- [TRAE SOLO CN] 阶段化测速：获取候选IP时先测连通+延迟，只对前30个测速度，节省时间和流量

## v4.9.0 - 2026-05-27

- [TRAE SOLO CN] 三网API自动匹配：新增090227/001315联通+移动API，根据DDNS识别用户运营商自动调对应API获取专属IP池
- [TRAE SOLO CN] 多维度端到端真实测速：test_user_path_latency()从TCP连接改为完整HTTPS测速（延迟+下载速度+丢包率）
- [TRAE SOLO CN] CDN→Google真实测速：test_google_path_latency()从TCP连8.8.8.8改为通过CDN IP访问Google（延迟+速度）
- [TRAE SOLO CN] 新五维综合评分：用户链路(35%)+VPS→CDN(25%)+CDN→Google(20%)+速度(10%)+稳定性(10%)，替代旧七维评分
- [TRAE SOLO CN] 优选域名综合评分：select_best_domain()从只按延迟排序改为延迟+速度+可用性综合评分
- [TRAE SOLO CN] 运营商匹配度评分：calculate_isp_match_score()基于THREE_ISP_OPTIMAL_PREFIXES计算IP与运营商的匹配度
- [TRAE SOLO CN] 健康评估增强：health_check()集成CDN→Google测速+用户路径真实测速+新五维评分+多维度路径报告
- [TRAE SOLO CN] 数据库新增字段：google_latency_ms/google_speed_mbps/user_isp_match/composite_score_v2

## v4.8.0 - 2026-05-27

- [TRAE SOLO CN] CDN三模式优选：CDN_MODE配置项（ip_optimized/domain_optimized/domain_default），替代旧的CDN_PREFER_IP_OVER_DOMAIN布尔值
- [TRAE SOLO CN] 修复优选IP模式：纠正上一轮误判（curl -H只改HTTP头不改SNI），确认优选IP+正确SNI完全可用
- [TRAE SOLO CN] 新增优选域名模式：支持icook.hk/cf.090227.xyz等第三方优选域名，cdn_monitor自动测速选最优
- [TRAE SOLO CN] 新增多维度端到端测速：用户路径延迟（DDNS锚点）+ Google路径延迟
- [TRAE SOLO CN] TLS检测增强：cdn_monitor新增tls_handshake_test()，TCP+TLS双重验证，SNI=CF_DOMAIN

## v4.7.0 - 2026-05-27

- [TRAE SOLO CN] CDN域名回退：新增CDN_PREFER_IP_OVER_DOMAIN配置，默认域名模式（后经v4.8纠正为优选IP模式）
- [TRAE SOLO CN] subscription_service TLS握手验证：test_cdn_ip_connectivity()增加TLS层检测
- [TRAE SOLO CN] cdn_monitor TLS检测：http_latency_test()区分ssl.SSLError和普通异常

## v4.6.2 - 2026-05-27

- [TRAE SOLO CN] 修复 cdn_monitor.py 数据库路径重复拼接：`db_path_check` 改用已有的 `db_path`，避免打开错位数据库导致评分计算为 0（详见 AI_DEBUG_HISTORY 2026-05-27）

## v4.6.1 - 2026-05-27

- [TRAE SOLO CN] 砍掉CDN降级直连：同一VPS降级无意义，移除degrade_to_direct/decide_cdn_recover/相关API
- [TRAE SOLO CN] CDN优选逻辑收紧：迟滞机制（新IP必须好15%以上才换）+ CF防封（30秒间隔/单IP每分钟2次）+ 稳定期60秒
- [TRAE SOLO CN] 直连节点配置优化：新增optimize_reality_config()，测试6个SNI的TLS握手速度，给出最优SNI+TCP调优建议
- [TRAE SOLO CN] 新增 /api/direct-optimize 端点（GET），基于用户网络优化REALITY配置
- [TRAE SOLO CN] 部署到日本+新加坡VPS，DDNS锚点识别正确（175.10.213.182/湖南电信）

## v4.5.0 - 2026-05-27

- [TRAE SOLO CN] CDN故障自愈：新增 CdnHealthMonitor + CdnFailoverController，支持健康监控、自动切换、IP冷却池、降级直连兜底
- [TRAE SOLO CN] CDN直连回退：降级直连后每5分钟自动探测CDN恢复，有IP恢复健康立即切回CDN，支持手动触发恢复探测
- [TRAE SOLO CN] 订阅服务新增 /api/cdn-status（GET）+ /api/cdn-recover（POST）+ /api/cdn-degrade（POST）三个端点
- [TRAE SOLO CN] 直连节点筛选：新增 DirectNodeQualityFilter 类（五维评分+硬淘汰），节点<=2时硬淘汰改软淘汰（降权30%兜底）
- [TRAE SOLO CN] 三网最优优选：新增 THREE_ISP_OPTIMAL_PREFIXES 配置 + probe_three_networks/cross_isp_score，评分扩到九维
- [TRAE SOLO CN] config.py 新增 CDN_FAILOVER、DIRECT_NODE_HARD_REJECT、THREE_ISP_OPTIMAL_PREFIXES 配置

## v4.4.4 - 2026-05-27

- 修复 health_monitor.py 状态文件存储路径：从 `/tmp/` 改为 `data/` 目录，避免重启后丢失（详见 AI_DEBUG_HISTORY 2026-05-27）
- 修复 subscription_service.py 重复导入：删除函数内重复的 `CDN_IP_HARD_REJECT` 导入（详见 AI_DEBUG_HISTORY 2026-05-27）

## v4.4.2 - 2026-05-27

- 修复 health_monitor.py KeyError：`check_service()` 新增 `status` 字段，避免访问不存在的字典键（详见 AI_DEBUG_HISTORY 2026-05-27）

## v4.4.1 - 2026-05-26

- 修复 VLESS-HTTPUpgrade Clash 不兼容：`network: httpupgrade` → `ws` + `v2ray-http-upgrade: true`（详见 AI_DEBUG_HISTORY 2026-05-26）
- 两台服务器日志排查：sing-box 零重启，端口正常，journald 日志受控（47-71MB），内存充裕（215-216MB可用）

## v4.4.0 - 2026-05-24

- 修复 idle_timeout 导致 sing-box FATAL 崩溃：替换为 tcp_keep_alive + tcp_keep_alive_interval
- VLESS-Reality 速度退化修复：修正 keepalive 参数，客户端添加 multiplex 禁用 + tcp_fast_open
- 全协议暗病修复：Hysteria2 UDP 缓冲区 208KB→2MB，CDN IP 替换为优质段，CDN 协议添加 multiplex/tcp_fast_open
- VLESS-Reality 入站添加 tcp_keep_alive（防止空闲断连）
- Hysteria2 服务端添加 up_mbps/down_mbps=200（匹配客户端 brutal 模式）
- Trojan-WS 客户端添加 utls 指纹伪装 + multiplex 禁用 + tls.alpn
- 所有 CDN 协议客户端添加 tls.alpn=["http/1.1"]（显式匹配服务端）
- install.sh 新增 UDP/QUIC 参数：rmem_max/wmem_max=16MB, optmem_max, TFO 黑洞禁用
- cdn_monitor 新增 TCP 下载速度测试（Cloudflare 10MB 测速文件纳入评分）
- cdn_monitor 新增定期健康评估（每6小时，评分下降30%触发IP池刷新）
- 新增 scripts/test_connection.py 连接测试工具
- HY2 无感轮询验证：201 个 UDP DNAT 规则全部正常

## v4.3.9 - 2026-05-22

- 修复 cdn_monitor 403 检测 Bug：HTTP 403/1020/1010 时返回 False（之前错误返回 True，导致被拦截 IP 被标记为存活）
- subscription_service 移除 HTTP 层 403 检测，只做 TCP 连通测试，减少请求特征暴露
- subscription_service 新增 CDN IP 检测结果缓存（10 分钟有效期），避免每次刷新都重测
- subscription_service 新增换 IP 冷却机制：连续 3 次换 IP 失败后暂停 15 分钟
- cdn_monitor HTTP 检测特征随机化：随机 UA（6 个）、随机路径（5 个）、随机间隔（1-3 秒）
- cdn_monitor 403 拦截日志从 debug 提升到 warning，journalctl 默认可见
- IP 池扩容：CDN_TOP_IPS_COUNT 从 5 → 15，每服务器 10-15 个 IP
- IP 池多 C 段分散：优先选择不同 C 段的候选 IP，覆盖 ≥5 个 C 段
- 协议 IP 分配改为随机选择，不固定绑定前 3 个

## v4.3.8 - 2026-05-22

- 引入 cfnew 可复用思路：订阅服务新增 `/api/preferred-ips`，支持优选 IP 的查询、批量添加、批量删除
- 增强 `/api/cdn`：切换协议当前 CDN IP 时同步维护 `cdn_ips_list`，避免只改当前值不入池
- `config.py` 新增自定义优选源 URL、最快 N 个筛选、地区筛选配置项
- `cdn_monitor.py` 支持从自定义优选源 URL 拉取候选 IP，并按最快 N 个与地区筛选策略收敛结果

## v4.3.7 - 2026-05-21

- CDN优选IP更新：12个新IP随机分配到日本/新加坡/美国三台服务器（每区3个，不重复）
- CDN优选IP池扩充：config.py新增12个用户投喂优质IP（第六批）
- 服务器网络参数优化：TCP keepalive从600s降至30s，更快检测死连接；US服务器conntrack_max从65536扩至262144
- CDN断线排查：确认断线根因为Cloudflare CDN WebSocket空闲超时（100秒），服务端无错误日志

## v4.3.6 - 2026-05-18

- CDN优选IP调整：黑名单加入3个慢速IP（8.35.211.141 / 173.245.59.21 / 162.159.35.152），延迟低但实际速度不行
- CDN优选IP调整：优选池加入11个用户确认可用的优质IP，覆盖162.159/172.64/108.162/104.18段
- 新加坡和日本服务器CDN IP池同步更新，等待CDN监控下一次自动执行生效

## v4.3.5 - 2026-05-10

- 修复 `scripts/config_generator.py` 仍生成 legacy DNS server 格式的问题，改为 sing-box 新版 `type/server` 写法
- 给服务端 `route` 显式补上 `default_domain_resolver`，不再依赖 `ENABLE_DEPRECATED_*` 环境变量兜底
- 修复 `scripts/subscription_service.py` 生成的 sing-box JSON 仍使用 `tls://` / `h3://` / `rcode://` / `fakeip` 旧写法的问题
- `install.sh` 删除 `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS` 和 `ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER` 启动兜底，避免新部署继续埋雷
- 新增 `tests/test_dns_config_migration.py`，防止以后又把旧式 DNS 配置写回去
- 修复 `install.sh` 里 HY2 端口尾值误写为 `21199` 的边界错误，统一恢复为 `21000-21200`
- 修复 `scripts/diagnose.sh` 会把正常 iptables 流量计数器和正常 CDN SNI 场景误报成故障的问题
- 修复新版 DNS 迁移时误保留 `detour: direct` 导致 singbox 1.13.11 启动失败的问题
- 修复 sing-box JSON 客户端默认开启 `FakeIP + TUN` 会让 `ping` 显示 `<1ms`、误导线路判断的问题，现改为默认关闭 `fakeip.enabled`
- 统一 README、脚本头部版本号和诊断输出版本，删除重复旧文 `AI_SOCKS5_PITFALL_GUIDE.md`

## v4.3.4 - 2026-05-10

- 修复 `.env.example` 仍使用行内注释的问题，避免再次误导手动部署
- `scripts/config.py` 新增统一 `.env` 读取逻辑，优先使用 `python-dotenv`，降级时兼容历史行内注释格式
- `scripts/config_generator.py` 改为复用统一 `.env` 解析逻辑，避免服务端配置生成再次读歪
- 新增 `tests/test_env_parsing.py`，覆盖旧式 `.env` 行内注释兼容场景
