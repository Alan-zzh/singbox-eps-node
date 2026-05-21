# AI 调试历史与防Bug规则 (AI Debug History)

##  最新排查（2026-05-22）

### CDN 阻断根因修复 [Trae CN]
- **现象**: 日本/新加坡 CDN 节点同时被 Cloudflare 临时拦截（403/1020），持续约 30 分钟后自动恢复
- **根因**:
  1. cdn_monitor `http_latency_test` 在 403 时返回 True（Bug），被拦截 IP 被标记为存活，无法触发替换
  2. subscription_service 每次刷新订阅都发 HTTP 请求检测 403，固定 UA+固定路径被 CF 识别为爬虫
  3. IP 池只有 3 个且集中在 2 个 C 段，一拦全拦
  4. 换 IP 机制没有冷却期，每 5 分钟重试反而加重拦截
- **修复**:
  - cdn_monitor 403 检测返回 False + 日志提升到 warning
  - subscription_service 移除 HTTP 检测只做 TCP + 10 分钟缓存 + 15 分钟冷却
  - cdn_monitor 随机化 UA/路径/间隔
  - IP 池扩容到 10-15 个 + 多 C 段分散 + 随机分配
- **教训**: HTTP 自动化检测请求特征太明显会触发 CF WAF，检测频率越高风险越大；403 检测应集中在低频的 cdn_monitor 而非高频的 subscription_service

### cfnew 源码接入评估 [Trae CN]
- **目标**: 评估并引入 `byJoey/cfnew` 中可复用的优选 IP 管理能力，而不是整仓替换当前 Python + SQLite 架构
- **排查过程**:
  1. clone `byJoey/cfnew` 到本地临时目录，仅做源码拆解
  2. 核心源码集中在 Worker 单文件 `明文源吗`，并非可直接落地的 Python 模块
  3. 确认可复用的重点能力：优选 IP API 管理、自定义优选源 URL、最快 N 个筛选、地区筛选思路
  4. 确认不适合直接移植：KV 图形面板、Worker fallback、ECH 获取、path 参数覆盖（与当前架构耦合过深）
- **本次落地**:
  - `subscription_service.py` 新增 `/api/preferred-ips`，支持查询、批量添加、批量删除优选 IP
  - `/api/cdn` 切换协议当前 IP 时同步维护 `cdn_ips_list`
  - `config.py` 新增 `CDN_CUSTOM_SOURCE_URLS`、`CDN_FASTEST_LIMIT`、`CDN_REGION_FILTER`
  - `cdn_monitor.py` 支持自定义优选源 URL 拉取与最快 N 个筛选
- **验证结果**:
  - `py_compile` 通过
  - 本地测试脚本运行通过，但本地数据库没有现网 CDN 配置，导致“单个 IP 被阻断自动换 IP”场景无法在本地完整复现，这属于测试数据缺失，不是代码语法错误
- **经验**:
  - Worker / KV 项目不要整仓硬搬到 Python / SQLite 项目
  - 应只抽取“数据接口与筛选策略”这一层能力，避免引入大量不兼容运行时逻辑

##  最新排查（2026-05-22）

### Cloudflare自动拦截问题 [Trae CN]
- **现象**: 用户反馈CDN节点间歇性集中断线，本地ping没问题
- **排查过程**:
  1. 检查Cloudflare Dashboard：Under Attack Mode已关闭，Bot Fight Mode不可见（免费版无此选项）
  2. 从本地测试：TCP通、SSL通、但WebSocket请求被403拦截
  3. 根因确认：Cloudflare风控学习期结束后（域名启用2-4周），自动化威胁检测系统开始标记代理流量
  4. 社区调研：Cloudflare从2025年底系统性打击CDN跑代理，免费版无法关闭自动化防护
  5. 结论：这不是配置问题，是Cloudflare平台层面的限制，无法彻底解决
- **已做优化**:
  - 自动降级恢复：检测CDN IP 403时自动回退到域名
  - CDN IP自动轮换：cdn_monitor每小时自动换一批IP
  - 403/1020检测：自动标记并淘汰被Cloudflare拦截的IP
  - 智能IP筛选：自动剔除被拦截的IP，保留高质量IP
- ** 建议**:
  - 主用Reality协议（不经过Cloudflare，完全稳定）
  - CDN作为备用，自动轮换可以续命几天到几周
  - 需要稳定长连接时用Reality，CDN适合日常浏览

## 🆕 最新排查（2026-05-21）

### CDN频繁断线排查 [Trae CN]
- **现象**: 用户反馈"动不动CDN的就断线"，但本地ping完全没问题
- **排查过程**:
  1. SSH到三台服务器检查sing-box日志（/var/log/singbox.log，不是journalctl）
  2. CDN协议（vless-ws/vless-upgrade/trojan-ws）服务端无任何断线错误日志
  3. SG服务器有大量Reality协议mux连接重置（86次/小时，来自用户IP 113.247.86.236）
  4. US服务器有36次127.0.0.1 Reality握手错误（健康检查脚本触发，正常）
  5. 所有CDN入站协议均未配置idle_timeout
  6. TCP keepalive_time=600s（太长），US服务器conntrack_max=65536（太小）
- **根因**: Cloudflare CDN WebSocket空闲超时（100秒）——空闲100秒后Cloudflare主动关闭WebSocket，服务端看到的是正常关闭不记录错误，客户端则感知为断线。ping走ICMP不受影响
- **已做优化**:
  - TCP keepalive: 600s→30s, intvl: 30s→10s, probes: 10→3（更快检测死连接）
  - US conntrack_max: 65536→262144
  - 持久化到 /etc/sysctl.d/99-singbox-optimize.conf
- **建议**:
  - 客户端应避免长时间空闲（浏览网页时一般没问题，但挂机/下载暂停场景容易触发）
