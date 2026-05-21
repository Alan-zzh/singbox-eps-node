# AI 调试历史与防Bug规则 (AI Debug History)

## 🆕 最新修复（2026-05-10）

### Bug #90: sing-box JSON 客户端默认开启 `FakeIP + TUN`，会把延迟判断彻底带偏
- **问题**: `subscription_service.py` 生成的 sing-box JSON 默认开启了 `dns.fakeip.enabled = true`，同时又默认带 `tun` 入站。这样用户在 v2rayN / sing-box TUN 模式里 ping 某些域名或节点相关目标时，命中的可能是本机分配的 FakeIP，而不是真实远端线路，容易出现 `<1ms` 这种明显不符合跨国链路常识的结果。
- **影响**:
  - 用户会误以为"新加坡明明走日本，为什么延迟还不到 1ms"，从而怀疑节点地区、路由、DNS 全部写错
  - 延迟指标被 FakeIP 污染后，用户很难判断到底是 CDN 差、直连差，还是客户端指标本身失真
  - TUN 场景下部分应用还可能出现"体感卡，但 ping 很漂亮"的错觉，排查方向会被严重带偏
- **修复**:
  - `scripts/subscription_service.py` 生成的客户端 sing-box JSON 改为默认关闭 `dns.fakeip.enabled`
  - 保留 FakeIP 结构和地址段定义，后续如确有明确需求再单独按场景开启，不再默认对所有用户生效

### Bug #89: 新格式DNS迁移时把 `detour: direct` 误带进来了，导致日本机 singbox 直接起不来
- **问题**: 这次把 DNS 从旧 `address` 写法迁到 sing-box 新格式时，沿用了旧时代的 `detour: "direct"` 思路。但 sing-box 1.13.11 对新版 DNS server 直接报错：`detour to an empty direct outbound makes no sense`
- **影响**:
  - 日本服务器 `singbox` 主服务持续重启，443/8443/2053/2083 全部掉线
  - `singbox-sub` 仍然能回 200，所以表面像"订阅还活着"，但真正代理节点已经没网
  - 如果把同样代码继续推到其他服务器，会复制同一个现网故障
- **修复**:
  - `scripts/config_generator.py` 删除新版 DNS server 上的 `detour: "direct"`
  - `scripts/subscription_service.py` 生成的客户端 sing-box JSON 同步删除这两个 DNS server 的 `detour`
  - 保留 `route.default_domain_resolver` 和 `dns_direct.domain_resolver`，只去掉错误的 `detour`

### Bug #87: singbox当前正常，但仍靠 deprecated DNS 兼容开关硬撑
- **问题**: 日本服务器当前 `singbox` 虽然是 active，但去掉 `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS` 后 `sing-box check` 直接失败，说明 `config_generator.py` 仍在生成旧式 DNS server 写法，`subscription_service.py` 生成的客户端 JSON 也还是 `tls://` / `h3://` / `rcode://` / `fakeip` 老格式
- **影响**:
  - 眼下不算现网故障，因为 systemd 里有 `ENABLE_DEPRECATED_*` 兜底，用户侧也基本正常
  - 但这是典型"慢性复发型"暗病，一旦 sing-box 升到 1.14，兼容开关被删，`singbox` 会再次直接起不来
  - 新部署如果继续沿用 `install.sh` 里的兼容开关，也会把旧坑原样复制到下一台服务器
- **修复**:
  - `scripts/config_generator.py` 改成 sing-box 新版 DNS server 格式：`type/server` 取代旧 `address`
  - 服务端 `route` 显式补上 `default_domain_resolver`
  - `scripts/subscription_service.py` 生成的客户端 JSON 同步迁移到新版 DNS 格式，并给 `dns_direct` 补 `domain_resolver`
  - `install.sh` 删除 `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS` 和 `ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER`
  - 新增 `tests/test_dns_config_migration.py`，防止以后回退到旧格式

### Bug #88: install/diagnose 仍有边界错误和误报，容易把人带沟里
- **问题**:
  - `install.sh` 里部分 iptables 规则仍写成 `21000:21199`，和实际端口跳跃范围 `21000:21200` 差了最后一个端口
  - `diagnose.sh` 用 `grep -c ... || echo 0` 统计流量计数器，没命中时会得到 `0\n0`，导致脚本自己报 `integer expression expected`
  - `diagnose.sh` 直接访问 `https://IP:2087` 测 CDN IP，会被证书/SNI 机制误伤，把正常 CDN 误判成故障
  - `diagnose.sh` 把 `fullchain.pem` 不存在单独当警告，但当前项目允许 `cert.pem` 正常兜底，这条提示容易制造噪音
- **影响**:
  - 新部署时 21200 这个尾端口可能漏放行，属于低概率但真实存在的边界暗病
  - 诊断脚本会平白报 4-5 个失败项，误导后续排查方向
  - 人会以为线上坏了，实际只是诊断逻辑自己不准
- **修复**:
  - `install.sh` 统一改成 `21000:21200`
  - `diagnose.sh` 改正 iptables 计数器匹配逻辑
  - CDN 连通性检测改成 `--resolve 域名:端口:IP`，带域名 SNI 做真测试
  - 证书检查改成 `fullchain.pem` / `cert.pem` 二选一即可，不再把正常兜底当警告

### Bug #86: `.env.example` 仍带行内注释，手动复制后有复发风险
- **问题**: 仓库里的 `.env.example` 仍是 `KEY=  # 注释` 格式。虽然 `install.sh` 现在会生成干净 `.env`，但用户手动复制示例文件或人工补配置时，`config.py/config_generator.py` 的旧手写解析逻辑仍可能把注释误读成值
- **影响**:
  - `AI_SOCKS5_PORT` 这类数字字段可能再次触发 `ValueError`
  - `CF_DOMAIN`、`REALITY_PUBLIC_KEY` 等字符串字段可能被读成带注释脏值
  - 新部署不一定复现，手改配置时更隐蔽，属于"慢性复发型"问题
- **修复**:
  - 清理 `.env.example` 的所有行内注释，改为独立注释行
  - `config.py` 新增统一 `.env` 读取逻辑，优先 `python-dotenv`
  - `config_generator.py` 改为复用 `config.py` 的统一解析逻辑
  - 补充最小测试覆盖旧式行内注释兼容场景

### Bug #85: singbox-cdn死循环重启1492次
- **问题**: crontab每小时执行 `systemctl restart singbox-cdn`，但cdn_monitor --daemon已在运行中。新实例检测到锁文件后正常退出(exit 0)，systemd的Restart=always又把它拉起来，形成死循环
- **影响**: 每5秒重启一次，累计1492次，浪费CPU和日志空间
- **修复**:
  - 删除crontab中 `0 * * * * /usr/bin/systemctl restart singbox-cdn` 条目
  - systemd service: Restart=always → Restart=on-failure
  - pkill旧进程 + 删锁文件 + 重启服务
  - install.sh同步修改Restart=on-failure

### Bug #84: install.sh硬编码CF API Token泄露
- **问题**: install.sh第33行硬编码Cloudflare API Token，推到GitHub公开仓库会泄露
- **影响**: 任何人可拿到Token操作你的Cloudflare DNS
- **修复**: CF_DEFAULT_API_TOKEN改为从环境变量CF_API_TOKEN读取，无值时交互式询问用户输入

### Bug #83: config.py缺少AI_SOCKS5_POOL变量定义
- **问题**: subscription_service.py和config_generator.py都引用AI_SOCKS5_POOL，但config.py没有定义
- **影响**: 违反唯一真相源规则，其他文件只能自己读.env
- **修复**: config.py添加 AI_SOCKS5_POOL = os.getenv('AI_SOCKS5_POOL', '')

### Bug #82: REALITY_SHORT_ID/DEST/SNI导入后被覆盖
- **问题**: subscription_service.py从config.py导入了REALITY_SHORT_ID/DEST/SNI，但紧接着用os.getenv覆盖
- **影响**: config.py的值被丢弃，等于白导入。如果config.py有特殊逻辑（如默认值检测），这些逻辑全部失效
- **修复**: 删掉3行覆盖代码，直接使用config.py导入的值

### Bug #81: subscription_service.py多个变量不从config.py导入
- **问题**: COUNTRY_CODE、SUB_TOKEN、AI_SOCKS5_POOL自己用os.getenv读，不从config.py导入
- **影响**: 违反唯一真相源规则，如果config.py的默认值或读取逻辑变更，subscription_service.py不会同步
- **修复**:
  - COUNTRY_CODE/SUB_TOKEN/AI_SOCKS5_POOL加入config.py导入列表
  - ImportError降级块也补充这3个变量
  - parse_socks5_pool()改用导入的AI_SOCKS5_POOL变量
  - 删掉独立的COUNTRY_CODE定义行

### Bug #80: singbox-cdn未运行+CDN数据库缺失
- **问题**: 日本服务器singbox-cdn服务未运行，CDN数据库文件不存在
- **影响**: CDN优选IP无法自动更新，订阅中CDN节点可能失效
- **修复**: 启动singbox-cdn服务，创建SQLite数据库和表结构

### Bug #79: sing-box 1.12.0+ DNS配置格式不兼容
- **问题**: sing-box 1.13.9/1.13.11要求新的DNS服务器格式，旧格式启动失败
- **影响**: singbox无法启动，所有代理服务中断
- **修复**: systemd服务文件添加ENABLE_DEPRECATED_LEGACY_DNS_SERVERS和ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER环境变量

### Bug #78: REALITY协议100%握手失败
- **问题**: REALITY私钥/公钥不匹配，客户端TLS握手全部失败
- **影响**: REALITY节点完全不可用，客户端疯狂重试导致连接池占满，所有协议卡顿（1秒+延迟）
- **修复**:
  - 重新生成REALITY密钥对（日本+新加坡）
  - 更新.env和config.json
  - 重启singbox和订阅服务

### Bug #77: 新加坡CF_DOMAIN配置错误
- **问题**: 新加坡服务器.env中CF_DOMAIN=us.290372913.xyz（美国域名）
- **影响**: CDN节点SNI使用美国域名，流量绕道美国，客户端连不上
- **修复**: 改为sg.290372913.xyz，重启所有服务

### Bug #76: AWS MTU 9001导致所有协议卡顿
- **问题**: AWS云服务器默认MTU 9001（Jumbo Frames），客户端MTU 1500
- **影响**: 数据包分片，UDP丢包严重，TCP重传率高，所有协议卡顿
- **修复**:
  - MTU改为1500（日本+新加坡）
  - UDP缓冲区优化：rmem_max/wmem_max从212KB提升到25MB
  - 创建永久生效配置（/etc/network-optimization.sh + rc.local + sysctl.d）

### Bug #75: CDN IP黑名单更新
- **问题**: 用户反馈多个CDN IP延迟高/连不上
- **修复**: 加入黑名单：104.16.147.135、104.17.119.190、104.17.110.132、104.16.244.71、162.159.152.11

---

## ⚠️ AI 编码铁律（必须遵守）

### 规则1：HTTPS服务必须使用域名访问，禁止用IP
**教训来源**: v1.0.43 使用IP地址访问HTTPS订阅
**Bug现象**: V2rayN等客户端验证SSL证书时，发现证书颁发给域名，与访问的IP不匹配，拒绝连接（SEC_E_WRONG_PRINCIPAL）
**正确做法**: 使用域名访问（走CDN，证书匹配）
**判断标准**:
- 任何HTTPS服务，如果SSL证书是颁发给域名的，访问地址必须用域名
- 订阅链接必须用域名格式：https://{CF_DOMAIN}:{SUB_PORT}/sub/{国家代码}

### 规则12：安装脚本必须严格按依赖顺序执行
**教训来源**: v1.0.52 安装脚本中setup_firewall在setup_port_hopping之前执行
**Bug现象**: iptables -F清空刚设置的端口跳跃规则，导致HY2端口跳跃失效
**正确做法**: 先设置端口跳跃规则，再配置防火墙
**判断标准**:
- 端口转发规则必须在防火墙重置之前设置
- 安装脚本执行顺序：端口跳跃 → 防火墙 → 服务启动
- 用IP访问HTTPS = 证书域名不匹配 = 客户端拒绝连接

### 规则2：订阅服务端口必须在Cloudflare CDN支持列表中
**教训来源**: v1.0.43 使用9443端口，CDN不代理
**Bug现象**: 通过域名:9443访问时，CDN不转发流量，直接丢弃
**Cloudflare CDN支持的HTTPS端口**: 443, 2053, 2083, 2087, 2096, 8443
**正确做法**: 订阅服务端口必须从上述列表中选择，确保域名访问可走CDN

### 规则3：端口修改必须三同步
**教训来源**: v1.0.42之前默认端口6969导致防火墙不匹配
**Bug现象**: 代码默认端口、.env配置、iptables规则三者不一致
**正确做法**: 修改端口时必须同步更新：
1. config.py中的硬编码值
2. .env中的SUB_PORT
3. .port_lock锁定文件（运行save_port_lock()）
4. health_check.sh中的端口检查
5. iptables规则（虽然现在默认全放行，但仍需确认）

### 规则4：修改任何配置前必须先查快照和病历本
**教训来源**: 多次重复踩坑
**正确做法**: 每次修改前先读 project_snapshot.md 和 AI_DEBUG_HISTORY.md，复用已有方案，避免已踩过的坑

### 规则5：测试必须模拟真实客户端环境
**教训来源**: v1.0.43用curl -k测试通过，但V2rayN不用-k
**Bug现象**: curl -k跳过证书验证能通，但V2rayN验证证书失败
**正确做法**: 测试HTTPS服务时，必须不使用-k/--insecure参数，模拟真实客户端的证书验证行为

### 规则6：禁止硬编码IP/域名/凭据/路径
**教训来源**: v1.0.45前代码中硬编码了域名、服务器IP、SOCKS5凭据、文件路径
**Bug现象**: 新VPS部署时必须手动修改大量代码，极易遗漏导致服务异常
**正确做法**:
- 所有IP/域名从.env读取（SERVER_IP自动检测，CF_DOMAIN从.env读取）
- 所有凭据从环境变量读取
- 所有文件路径从config.py的BASE_DIR/CERT_DIR拼接
- 订阅域名统一使用 `get_sub_domain()` 获取

### 规则7：CDN IP获取必须使用指定DNS
**教训来源**: v1.0.36-37使用日本服务器DNS解析，返回对中国延迟高的IP
**Bug现象**: CDN优选IP对中国用户延迟高达200ms+
**正确做法**: 使用指定DNS（222.246.129.80 | 59.51.78.210，湖南电信DNS），这些DNS返回对中国用户延迟最低的Cloudflare IP

### 规则8：HY2端口跳跃必须UDP+TCP双规则，目标必须与listen_port一致
**教训来源**: v1.0.45前cert_manager.py将21000-21200转发到4433，但HY2监听443；后来修复时又错误地移除了TCP规则
**Bug现象**:
- 端口跳跃的流量到达4433端口，但HY2不在4433监听，导致端口跳跃功能完全无效
- 只设UDP规则时，UDP被封则HY2完全不可用，无TCP兜底
**正确做法**:
- iptables DNAT目标端口必须与config_generator.py中HY2的listen_port一致（当前为443）
- mport参数范围必须与iptables规则范围一致（当前为21000-21200）
- HY2端口跳跃必须同时设置UDP和TCP规则：
  - UDP：HY2核心协议(QUIC)，主要流量走UDP
  - TCP：降级兜底，UDP被封或不稳定时HY2可降级使用TCP
  - 双协议保障：UDP不通→TCP兜底，TCP不通→UDP兜底

### 规则9：跨文件配置必须保持一致性
**教训来源**: v1.0.45前HY2配置在cert_manager.py、subscription_service.py、config_generator.py三处不一致
**Bug现象**: 端口跳跃范围21000-21200 vs 22000-22200，目标端口4433 vs 443
**正确做法**:
- 修改任何配置时，必须全局搜索所有引用该配置的文件
- 使用config.py中的常量作为唯一真相源（Single Source of Truth）
- 修改配置后必须验证所有引用点的一致性

### 规则10：改代码必须同步更新文档（强制红线）
**教训来源**: v1.0.45中SOCKS5 AI路由规则代码已实现但文档未记录；TECHNICAL_DOC.md严重过时（还是硬编码IP/域名）；HY2双协议保障未在文档中说明导致AI错误移除TCP规则
**Bug现象**:
- 文档过时 → 下一个AI基于过时文档做判断 → 犯错（如移除TCP规则）
- 功能未记录 → AI不知道该功能存在 → 重复开发或误删
- 文档与代码不一致 → 文档失去参考价值 → 形同虚设
**正确做法**（每次改代码必须执行，不可跳过）:
1. **改代码前**: 先查 project_snapshot.md 和 AI_DEBUG_HISTORY.md
2. **改代码时**: 代码注释必须说明设计意图（为什么这样做，不只是做了什么）
3. **改代码后**: 必须同步更新以下文档：
   - `project_snapshot.md`: 版本号+1，记录改了什么
   - `AI_DEBUG_HISTORY.md`: 如果修了Bug，新增Bug记录和铁律
   - `TECHNICAL_DOC.md`: 如果涉及架构/功能/配置变更，更新对应章节
4. **验证**: 确认文档内容与代码实际行为一致，不允许"代码改了文档没改"

### 规则11：区分"用户可见节点"和"幕后路由出站"（强制红线）
**教训来源**: v1.0.48中将AI-SOCKS5作为"节点"加入Base64订阅和selector列表
**Bug现象**:
- 用户在V2rayN节点列表中看到"AI-SOCKS5"节点，手动选择后无法正常使用
- AI-SOCKS5本质是一个出站代理链路，不是独立代理节点
- 用户选它=所有流量走SOCKS5=失去其他节点的分流能力，且SOCKS5本身可能不稳定
**根本原因**:
- 技术文档明确写了"无感路由，用户无需手动选择"，但AI只理解了"SOCKS5是个代理"的字面意思
- AI没有理解设计意图：SOCKS5是"幕后工作者"，只在路由规则里默默把AI流量牵制过去
- AI看到"SOCKS5"就当成"节点"塞进节点列表，完全忽略了"无感"这个关键词
**正确做法**:
1. **用户可见节点**（出现在Base64订阅和ePS-Auto selector中）：VLESS-Reality、VLESS-WS、VLESS-HTTPUpgrade、Trojan-WS、Hysteria2
2. **幕后路由出站**（只出现在sing-box JSON的outbounds和route.rules中）：AI-SOCKS5
3. 判断标准：如果一个出站的作用是"让特定流量自动走此出站，用户不需要手动选择"，那它就是幕后路由出站，不应暴露给用户
4. 禁止将幕后路由出站加入：Base64订阅链接、ePS-Auto selector可选列表、首页HTML节点列表

### 规则12：修改功能必须同步更新所有实现该功能的文件（强制红线）
**教训来源**: v1.0.50全面审查发现13个隐藏问题，根因是修改subscription_service.py时没有同步更新config_generator.py、tg_bot.py、README.md等
**Bug现象**:
- subscription_service.py的AI路由规则完整，config_generator.py缺少域名和排除规则
- subscription_service.py的SOCKS5出站用selector+socks双层结构，config_generator.py用单层socks
- tg_bot.py订阅链接端口硬编码6969，config.py已经改成2087
- README.md把AI-SOCKS5列为第6个节点，与铁律11冲突
**根本原因**:
- AI只修改了"正在处理的文件"，没有全局搜索所有引用该功能的文件
- 每个文件独立实现相同功能，没有统一引用config.py作为唯一真相源
- 修改后只更新了"主要文档"，没有检查README、TECHNICAL_DOC等所有文档
**正确做法**:
1. 修改任何功能前，必须全局搜索所有引用该功能的文件：`grep -r "关键词" scripts/ *.md`
2. 功能实现必须统一引用config.py作为唯一真相源，禁止各文件独立实现
3. 修改后必须检查所有相关文件是否需要同步更新：
   - subscription_service.py（订阅服务）
   - config_generator.py（配置生成器）
   - tg_bot.py（TG机器人）
   - README.md（公开文档）
   - TECHNICAL_DOC.md（技术文档）
   - health_check.sh（健康检查）
   - install.sh（安装脚本）

### 新增预防规则：路由规则顺序规范
- **教训来源**: Bug #25
- **正确做法**:
  - sing-box按顺序匹配route.rules，先匹配到的规则生效
  - 排除规则必须放在被排除的规则之前
  - 路由规则顺序应为：dns → private → 国内直连 → 排除规则 → AI规则 → final
  - 修改任何路由规则后必须检查前后规则是否有冲突
  - 客户端配置和服务端配置的路由逻辑要区分清楚（客户端用ePS-Auto，服务端用direct）

### 新增预防规则：DNS配置规范
- **教训来源**: Bug #23
- **正确做法**:
  - DNS服务器的detour必须设为direct，不能走代理
  - dns_proxy负责解析非国内域名，应该直连获取DNS结果
  - 最终流量走向由route.final规则控制，DNS不需要提前绕代理
  - DNS查询走代理会增加额外延迟，导致所有域名解析都变慢

---

## Bug 修复历史

### 近期 Bug 完整记录（#75-#90）

> 详见上方"最新修复"章节，Bug #75-#90 保留完整的问题/影响/修复描述。

### 历史 Bug 摘要表（#1-#74）

| Bug# | 版本 | 一句话摘要 |
|------|------|-----------|
| #1 | v1.0.38→v1.0.39 | Trojan-WS链接缺少insecure=1参数 |
| #2 | v1.0.36→v1.0.37 | CDN优选IP对中国用户延迟高（日本DNS解析） |
| #3 | v1.0.40→v1.0.41 | Trojan-WS协议不通（缺SSL+path编码不一致） |
| #4 | v1.0.41→v1.0.42 | 订阅端口9443从外部无法访问（三重bug叠加） |
| #5 | v1.0.43→v1.0.44 | V2rayN无法更新订阅（证书域名不匹配+9443不在CDN列表） |
| #6 | v1.0.44→v1.0.45 | CDN优选IP获取方式不正确（未用指定DNS） |
| #7 | v1.0.44→v1.0.45 | 代码硬编码导致新VPS部署困难 |
| #8 | v1.0.44→v1.0.45 | HY2端口跳跃目标端口错误（4433→443） |
| #9 | v1.0.48→v1.0.49 | AI-SOCKS5被错误地作为用户可见节点暴露 |
| #10 | v1.0.49→v1.0.50 | 跨文件配置不一致导致13个隐藏问题 |
| #11 | v1.0.50部署时 | HY2端口跳跃iptables端口范围错误+缺少TCP规则 |
| #12 | v1.0.51→v1.0.52 | 证书文件名不一致导致续签和检查形同虚设 |
| #13 | v1.0.48→v1.0.52 | install.sh防火墙全放行清除端口跳跃规则 |
| #14 | v1.0.52 | tg_bot.py运行CDN更新会死循环（while True脚本） |
| #15 | v1.0.52 | tg_bot.py设置住宅后不重启singbox-cdn |
| #16 | v1.0.52 | subscription_service.py硬编码覆盖config.py的HYSTERIA2_UDP_PORTS |
| #17 | v1.0.70→v1.0.71 | CAKE状态显示矛盾（verify未启用，summary硬编码已启用） |
| #18 | v1.0.71→v1.0.72 | reinstall命令逻辑错误（混淆应用密码和root密码） |
| #19 | v1.0.65→v1.0.66 | set -e导致CAKE失败时脚本直接退出 |
| #20 | v1.0.73→v1.0.74 | geoip/geosite在sing-box 1.12+已移除导致FATAL |
| #21 | v1.0.73→v1.0.74 | CAKE降级方案FQ不如FQ-PIE |
| #23 | v1.0.75→v1.0.76 | DNS代理查询导致延迟飙升（dns_proxy走ePS-Auto而非direct） |
| #24 | v1.0.76→v1.0.77 | CDN优选IP不自动更新（本地池永远优先，外部API永不触发） |
| #25 | v1.0.77→v1.0.78 | SOCKS5路由规则顺序错误导致X/推特/groK走错 |
| #26 | v1.0.77→v1.0.78 | SOCKS5缺少故障转移机制 |
| #28 | v1.0.80→v1.0.82 | AI规则包含google.com导致延迟测试走SOCKS5 |
| #29 | v1.0.82 | CDN优选IP返回104.x.x.x高延迟段（130ms+） |
| #30 | v1.0.82 | config_generator.py与subscription_service.py不同步 |
| #31 | v1.0.82 | CDN优选IP自动更新服务卡住（time.sleep挂住） |
| #32 | v1.0.83 | config_generator.py缺少DNS配置和final规则 |
| #33 | v1.0.83 | 旧面板残留进程和目录 |
| #34 | v1.0.84 | CDN重启crontab未写入install.sh |
| #35 | v1.0.85 | CDN本地IP池混入104.x.x.x高延迟段 |
| #36 | v1.0.85 | cert_manager续签后漏重启singbox-cdn |
| #37 | v1.0.85 | health_check漏检UDP端口（HY2/QUIC不可检测） |
| #38 | v1.0.85 | cdn_monitor数据库连接泄漏 |
| #39 | v1.0.85 | 414MB内存无Swap，OOM Killer杀掉进程导致掉线 |
| #40 | v1.0.85 | HUNAN_CT_OPTIMAL_PREFIXES包含未实测验证的IP段 |
| #41 | v2.0.0 | CDN优选IP硬过滤IP段导致优质IP被丢弃，判断规则反复调整不稳定 |
| #42 | v2.0.0 | 订阅响应缺少subscription-userinfo头，客户端看不到流量统计 |
| #43 | v2.0.0→v2.2.0 | CDN外部API高分IP实际延迟高，理论优选≠实际最优 |
| #44 | v2.2.0→v3.0.0 | CDN评分依赖理论值不反映真实表现，重构为v3.0学习系统 |
| #45 | v3.0.0→v3.0.1 | health_check.sh无执行权限导致健康检查完全失效 |
| #46 | v3.0.0→v3.0.1 | fwupd-refresh.timer未禁用导致fwupd反复重启触发OOM |
| #47 | v3.0.0→v3.0.1 | api.vvhan.com域名DNS失效(NXDOMAIN)，CDN数据源不可用 |
| #48 | v3.0.0→v3.0.1 | singbox凌晨因config.json不存在重启46次 |
| #49 | v3.0.1 | Windows CRLF换行符导致上传的shell脚本无法执行 |
| #50 | v3.0.1 | systemd ExecStartPre中cd命令路径解析错误 |
| #51 | v3.0.1 | cdn_monitor.py进程泄漏，5个孤儿进程浪费80MB内存 |
| #52 | v3.0.1 | VPS系统服务浪费大量内存(60MB+) |
| #53 | v3.0.4→v3.1.1 | 流量统计只显示几KB，改用iptables内核计数器替代Clash API |
| #54 | v3.1.1→v3.1.2 | config_generator.py路由规则不完整，缺少Google通用域名排除规则 |
| #57 | v3.1.1→v3.1.2 | CDN优选IP连上但没有纠错机制，用户无法通过更新订阅恢复 |
| #58 | v3.1.3 | 淘汰IP只标记不过滤，被淘汰IP仍可入选TOP5 |
| #59 | v3.1.3 | http_latency_test()异常路径socket泄漏 |
| #60 | v3.1.3 | ImportError降级块含104段IP+缺少必需变量 |
| #61 | v3.1.3 | assign_and_save_ips()数据库连接无try/finally |
| #62 | v3.1.3 | should_eliminate_ip()中last_success_time为None时跳过检查 |
| #63 | v3.1.3 | ip_test_history表无清理机制，数据库无限膨胀 |
| #65 | v3.1.3 | 新服务器部署时install.sh被绕过导致功能缺失 |
| #66 | v4.1.0 | AI路由强制内置不合理，改为可选项 |
| #74 | v3.1.3→v4.0.0 | CDN监控测试逻辑不合理，服务器测延迟不代表国内用户体验 |
