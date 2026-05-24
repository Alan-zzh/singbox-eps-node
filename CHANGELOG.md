# CHANGELOG

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
