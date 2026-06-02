# AI 调试历史与防Bug规则

## 最新排查（2026-06-03 v4.10.20.2）

### Reality 断连 — short_id 数组只放新值导致老客户端不通
- **现象**: 用户客户端用 abcd1234（v4.10.19 之前订阅），v4.10.20 把 short_id 改成新值后整站 Reality 断连
- **根因**: 改 short_id 时只用了 `secrets.token_hex(8)`，没保留旧 abcd1234 作为并存过渡
- **修复**: 远程直接重写 config.json 数组为 `["新值", "abcd1234"]`；本地代码加 `REALITY_SHORT_ID_LEGACY='abcd1234'` 并存逻辑
- **教训**: 任何"硬编码"值（密码/UUID/short_id/salt）变更时，必须先用**并存过渡**——新值加进去，旧值保留，**N 个版本后**再删旧值
- **端到端验证**: 发 TLS ClientHello with short_id=abcd1234 → TCP 0.08s + recv 超时（=Reality 协商中）= 匹配成功

## 历史排查（2026-06-03 v4.10.20）

### 服务器与本地代码脱节 4 个版本（v4.3.5 vs v4.10.20）
- **现象**: 服务器 VERSION=v4.3.5，本地=v4.10.20。subscription_service.py/cdn_monitor.py MD5 一致，但 cert_manager.py 和 diagnose.sh 差异
- **根因**: 历史部署只覆盖核心 .py，忽略辅助脚本（cert_manager.py/diagnose.sh/health_check.sh/requirements.txt）
- **修复**: 远程同步 cert_manager.py + diagnose.sh + health_check.sh + requirements.txt 到两台服务器
- **教训**: 服务器代码同步必须覆盖根目录文档 + scripts/ + 辅助脚本

### CDN 评分含两个永久为 0 的无效维度
- **现象**: google_latency_ms/google_speed_mbps 列存在但永远 0，无任何代码填充
- **根因**: v4.9 引入但用户路径测速从来不填，公式里加了权重就白算
- **修复**: 评分公式删除 google_* 权重；DROP COLUMN + 移除 ALTER TABLE（v4.10.20）
- **教训**: 评分维度必须全部有效，无效维度等于白算且拉低区分度

### Reality short_id 使用弱预设 abcd1234
- **根因**: install.sh 写死默认值
- **修复**: 默认值改 `secrets.token_hex(8)` 强随机
- **教训**: 任何用于认证的随机值都严禁使用硬编码弱预设

### health_check.sh 只输出"开始/完成"两行
- **根因**: 早期实现过于简单，故障时无法审计检查项细节
- **修复**: 重写为 8 项详细检查 + 完整日志输出到 logs/health_check.log
- **教训**: 守护脚本必须有审计日志，失败排查不能靠猜

### SQLite 默认 journal 模式导致多进程并发阻塞
- **根因**: singbox-sub 与 cdn_monitor 共用 singbox.db，subscript 读时 cdn_monitor 写会短期锁库
- **修复**: PRAGMA journal_mode = WAL（写不阻塞读）
- **教训**: SQLite 多进程并发场景必须用 WAL 模式

## 历史排查（2026-06-01 v4.10.19）

### 用户路径测速全部返回-ms/-Mbps（SNI修复方向错误）
- **现象**: v4.10.18将SNI改为USER_DDNS_DOMAIN后，所有15个CDN IP的user_path_result都是-ms/-Mbps
- **根因1**: SNI=USER_DDNS_DOMAIN不是Cloudflare域名，TLS握手虽成功但Cloudflare路由异常
- **根因2**: v4.10.19将SNI改回CF_DOMAIN后仍失败，因为Host=USER_DDNS_DOMAIN导致Cloudflare返回403
- **根因3**: Host=CF_DOMAIN也返回400，因为CDN 443端口跑的是sing-box，不提供HTTP服务
- **修复**: 移除HTTP请求，改为纯TCP+TLS握手测速。TLS握手成功即标记success=True
- **教训**: CDN 443端口不提供HTTP服务，不能通过HTTP响应判断CDN IP质量

### sysctl参数未持久化+SG缺少TCP优化
- **现象**: JP只有1项sysctl持久化，SG只有2项，两台default_qdisc=fq_pie
- **修复**: 两台服务器写入完整99-singbox.conf（18项参数），default_qdisc从fq_pie改为fq
- **教训**: TCP优化参数必须持久化到sysctl.d目录；BBR推荐搭配fq而非fq_pie

## 历史排查（2026-06-01 v4.10.18）

### CDN测速SNI缺失导致HTTPS握手失败
- **现象**: 服务器端curl测试CDN优选IP全部SSL handshake failure
- **根因**: curl直接用IP访问不发送SNI；Python代码SNI设为CF_DOMAIN而非用户域名
- **修复**: test_user_path_latency()优先使用USER_DDNS_DOMAIN作为SNI
- **教训**: CDN测速必须SNI=用户访问域名，Host=回源域名

### ISP匹配分user_isp_match全部为50.0无区分度
- **根因**: calculate_cross_isp_score()用精确IP匹配，但CDN优选IP是anycast IP不会出现在三网API返回的IP列表中
- **修复**: 增加C段前缀匹配（精确匹配优先，未命中则尝试/24前缀匹配）
- **教训**: anycast IP无法精确匹配，必须用前缀匹配

### ip_performance表2700+条死亡记录
- **修复**: health_check()末尾添加清理逻辑（consecutive_fails>5且composite_score_v2<10）+VACUUM压缩
- **教训**: 数据库需要定期清理死亡记录

## 历史排查（2026-06-01 v4.10.16）

### MemoryMin=50M被后续部署覆盖
- **根因**: 后续部署cdn_monitor.py时没有保留MemoryMin配置，systemd unit文件被覆盖
- **教训**: 部署新代码时必须检查systemd配置是否被覆盖

### 三网均衡度isp_score全为0
- **根因**: _three_isp_cache只在fetch_cdn_ips()步骤2填充，但health_check()独立调用时缓存为空
- **修复**: health_check()开始时检查缓存是否为空，为空则刷新
- **教训**: 全局缓存的生命周期必须覆盖所有使用场景

### 评分权重不合理导致优选IP变卡
- **根因**: 用户路径权重25%+25%=50%不够，实际评分被VPS侧和稳定性主导
- **修复**: 用户路径权重提升到35%+35%=70%
- **教训**: 用户路径才是真实体验指标，权重必须最大

## 历史排查（2026-05-31 v4.10.13-14）

### 真正根因：t3.nano 内存不足 + SG somaxconn 过小
- **现象**: 所有节点周期性全断，几分钟后恢复
- **根因**: 414MB RAM，sing-box RSS峰值99.6MB，内存触顶时内核swap出sing-box热内存→冻结→全断
- **修复**: MemoryMin=50M锁定物理内存 + GOMEMLIMIT=100MiB + GOGC=50 + SG somaxconn 4096→65536
- **教训**: 小内存VPS必须配MemoryMin+GOMEMLIMIT双保险；somaxconn默认值太小必须调到65536

### ~~以下为之前方向错误的诊断（v4.10.13-15，全部废弃）~~
- ~~Clash url-test参数回退导致闪断~~ — 根因是内存不足，不是Clash配置
- ~~Reality丢包20-40%~~ — 根因是内存不足导致swap冻结，不是Reality协议问题
- ~~keep-alive-interval/tcp-concurrent/unified-delay~~ — 在丢包环境下适得其反，已禁止恢复

## 历史排查（2026-05-30）

### Clash MATCH 规则指向 url-test 导致手动选择无效
- **根因**: MATCH指向自动选择(url-test组)，用户UI选择无实际效果
- **修复**: MATCH改为指向节点选择(select组)，节点选择首项为自动选择
- **教训**: MATCH规则必须指向select组，不能指向url-test组

### v4.10.4/v4.10.5 修复未部署到服务器
- **根因**: 本地改了但从未上传到远端服务器
- **教训**: 代码修复后必须立即部署到所有线上服务器

## 历史排查（2026-05-29）

### /api/cdn-status 500错误：_health_monitor作用域bug
- **根因**: `global` 指向模块级作用域，不是外层函数作用域
- **修复**: `global` → `nonlocal`
- **教训**: Python中变量定义在函数内部时，内嵌函数要用`nonlocal`而非`global`

### JP服务器HY2连接127.0.0.1:5151被拒绝（42万+次）
- **根因**: 客户端TUN模式将本地SOCKS5代理连接捕获并路由到代理隧道
- **修复**: 服务端路由规则添加私有地址拒绝规则
- **教训**: 服务端必须拦截私有地址代理请求

## 历史排查（2026-05-28）

### cdn_quality_filter.py 评分权重总和不等于1
- **修复**: cross_isp权重从0.15调整为0.14

### v4.10.2 高延迟IP被分配给用户
- **根因**: 存活≠质量好，fill_needed=0时评分更好的候选IP完全没机会替换
- **修复**: 改为从tested_results中取Top N，按评分排序分配
- **教训**: "存活"不等于"质量好"，筛选逻辑必须基于评分

### v4.10.1 订阅服务不返回优选IP
- **根因**: 长驻Flask进程没有感知数据库更新
- **修复**: cdn_monitor写入信号文件，subscription_service检测信号清缓存
- **教训**: 长驻进程必须有数据变更感知机制

## 历史排查（2026-05-27）

### CDN优选IP误判为失效
- **误判**: 用`curl -H 'Host'`测试，只改HTTP头不改SNI
- **正确方式**: `curl --resolve` 或 `openssl -servername`

### cdn_monitor.py 数据库路径重复拼接
- **修复**: 直接使用已有的db_path替代重复构造

## 历史排查（2026-05-26）

### VLESS-HTTPUpgrade Clash 不兼容
- **根因**: Clash Meta不支持`network: httpupgrade`，需用`ws` + `v2ray-http-upgrade: true`模拟
- **教训**: Clash Meta与sing-box传输层命名规则不一致

## 历史排查（2026-05-25）

### pkill 自杀导致 singbox-sub 永远无法启动
- **根因**: pkill匹配到自己的命令行并把自己杀掉
- **修复**: 改用`fuser -k 端口/tcp`
- **教训**: 绝对不要在ExecStartPre中使用`pkill -f "服务名.py"`

### nohup 幽灵进程占用端口导致systemd重启18861次
- **根因**: 旧nohup进程占着端口，systemd永远无法绑定
- **修复**: ExecStartPre清理残留进程 + health_monitor自动监控
- **教训**: 服务迁移启动方式时必须先清理旧进程

## 历史排查（2026-05-24）

### idle_timeout 导致 sing-box FATAL 崩溃
- **根因**: `idle_timeout`不是sing-box合法字段
- **修复**: 替换为`tcp_keep_alive` + `tcp_keep_alive_interval`
- **教训**: 新增sing-box字段前必须查官方文档确认合法性

## 历史排查（2026-05-22）

### CDN 阻断根因修复
- **根因**: cdn_monitor 403检测返回True(Bug) + 固定UA被CF识别为爬虫 + IP池只有3个
- **修复**: 403检测返回False + 移除HTTP检测只做TCP + 随机化UA/路径/间隔 + IP池扩容到10-15个
- **教训**: HTTP自动化检测请求特征太明显会触发CF WAF

### Cloudflare自动拦截问题
- **根因**: Cloudflare风控学习期结束后开始标记代理流量，免费版无法关闭
- **结论**: 不是配置问题，是Cloudflare平台层面限制
- **建议**: 主用Reality协议，CDN作为备用

## 历史排查（2026-05-21）

### CDN频繁断线排查
- **根因**: Cloudflare CDN WebSocket空闲超时（100秒）
- **修复**: TCP keepalive 600s→30s + US conntrack_max 65536→262144

## 关键教训汇总

1. **本地修改未部署 = 线上不生效**：必须同步部署到所有服务器
2. **SQLite迁移假成功**：迁移后必须核验表结构
3. **pkill自杀陷阱**：ExecStartPre中禁止pkill -f，改用fuser -k
4. **sing-box字段必须查文档**：禁止凭直觉猜测
5. **CDN 443端口不提供HTTP服务**：测速只能用TCP+TLS握手
6. **"推特私信发不出"先判平台限流**：不要只凭单一应用体感就改服务器
7. **数据格式变更必须同步所有读取端**
8. **长驻进程必须有数据变更感知机制**：信号文件最轻量
9. **小内存VPS必须配MemoryMin+GOMEMLIMIT双保险**
10. **评分维度必须全部有效**：无效维度等于白算
11. **global vs nonlocal**：变量定义在函数内部时内嵌函数要用nonlocal
12. **存活≠质量好**：筛选逻辑必须基于评分而非存活状态
13. **Clash Meta与sing-box传输层命名不一致**：httpupgrade需用ws+v2ray-http-upgrade模拟
14. **Cloudflare免费版无法关闭自动化防护**：主用Reality，CDN备用
