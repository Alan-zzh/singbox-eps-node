# AI 调试历史与防Bug规则 (AI Debug History)

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

### Bug #17: CAKE状态显示矛盾（verify显示未启用，summary硬编码已启用）
- **版本**: v1.0.70 → v1.0.71
- **日期**: 2026-04-22
- **现象**: verify_installation检测CAKE未启用（降级为FQ），但print_summary硬编码"CAKE队列: 已启用"
- **根因**: print_summary没有从实际检测结果读取CAKE状态，而是硬编码了"已启用"
- **修复**: print_summary从 `tc qdisc show dev $MAIN_IF` 实际检测读取状态
- **预防**: 状态显示必须从实际检测读取，禁止硬编码

### Bug #18: reinstall命令逻辑错误（声称不需要密码，但无法获取root密码）
- **版本**: v1.0.71 → v1.0.72
- **日期**: 2026-04-22
- **现象**: `bash install.sh reinstall` 声称"不需要输密码（自动从旧.env读取）"，但.env存储的是应用密码（VLESS_UUID/TROJAN_PASSWORD等），不是root密码，操作系统重装需要root密码
- **根因**: AI混淆了"应用密码"和"root密码"的概念。.env中的密码是代理协议密码，操作系统重装需要的是系统root密码，两者完全不同
- **修复**: 
  1. reinstall改为操作系统重装（集成bin456789/reinstall脚本）
  2. 添加root密码双重确认（连续输入两次，隐藏输入）
  3. 自动检测当前OS版本，重装为相同版本
  4. reset命令明确为singbox应用重装（保留配置和数据）
- **预防**: 区分"应用层密码"和"系统层密码"，操作系统重装必须要求用户输入root密码

### Bug #19: set -e导致CAKE失败时脚本直接退出
- **版本**: v1.0.65 → v1.0.66
- **日期**: 2026-04-22
- **现象**: 一键安装脚本运行到CAKE步骤就中断，后续所有步骤（TCP调优、文件描述符、安装singbox等）全部不执行
- **根因**: 脚本开头启用了 `set -e`，`tc qdisc replace` 在部分内核/VPS上不支持CAKE时返回非零退出码，导致脚本立即终止
- **修复**: 
  1. `tc qdisc replace` 改为 `cmd && CAKE_OK=true || true` 模式
  2. CAKE支持检测改为 `if modprobe sch_cake` + `tc qdisc add` 试探法
  3. 所有 `grep -q ... && sed || echo` 模式改为独立函数，用 `if/else` 替代
- **预防**: `set -e` 环境下所有可能失败的命令必须用 `|| true` 或 `if` 包裹

### Bug #20: geoip/geosite在sing-box 1.12+已移除，导致singbox FATAL退出
- **版本**: v1.0.73 → v1.0.74
- **日期**: 2026-04-22
- **现象**: 升级sing-box到1.13.9后，`FATAL: geoip database is deprecated in sing-box 1.8.0 and removed in sing-box 1.12.0`，所有代理端口未监听
- **根因**: config_generator.py和subscription_service.py仍使用`geoip`/`geosite`内联规则格式，sing-box 1.12.0彻底移除了该格式
- **修复**: 
  1. config_generator.py：删除`{"geoip":"cn"}`和`{"geosite":"cn"}`（服务端不需要）
  2. subscription_service.py：改用`rule_set`远程规则集格式（.srs二进制）
  3. 添加`rule_set`定义引用SagerNet/sing-geosite和sing-geoip
- **预防**: 升级sing-box大版本时必须检查配置格式兼容性，1.12+禁用geoip/geosite

### Bug #21: CAKE降级方案FQ不如FQ-PIE
- **版本**: v1.0.73 → v1.0.74
- **日期**: 2026-04-22
- **现象**: 内核不支持CAKE时降级为`fq`，但`fq_pie`比`fq`更适应高丢包环境
- **根因**: 初始实现时选了最基础的FQ作为降级方案，没有考虑FQ-PIE
- **修复**: `net.core.default_qdisc=fq` → `net.core.default_qdisc=fq_pie`
- **预防**: 降级方案应选择功能最接近原方案（CAKE=FQ+PIE）的替代品（FQ-PIE）

### Bug #23: DNS代理查询导致延迟飙升（dns_proxy走ePS-Auto而非direct）
- **版本**: v1.0.75 → v1.0.76
- **日期**: 2026-04-22
- **现象**: 代理服务器上测节点延迟很高，但本地连接显示延迟正常；所有流量（包括非AI网站）延迟都异常高
- **根因**: subscription_service.py中dns_proxy的detour设置为"ePS-Auto"，导致DNS查询走了代理节点→SOCKS5→多了一层代理→延迟飙升。dns_direct的detour是"direct"是正确的，但dns_proxy用错了
- **修复**: subscription_service.py第366行 `detour: "ePS-Auto"` → `detour: "direct"`
- **原理说明**:
  - dns_proxy（8.8.8.8）负责解析非国内域名，应该直连获取DNS结果，由后续路由规则决定流量走向
  - dns_proxy走ePS-Auto会导致DNS查询本身也绕代理，增加额外延迟
  - 最终路由（final: "ePS-Auto"）已经确保非国内/非AI流量走代理，DNS不需要提前绕代理
- **预防**: DNS服务器detour应设为direct，最终流量走向由route.final规则控制

### Bug #24: CDN优选IP不自动更新（本地池永远优先，外部API永不触发）
- **版本**: v1.0.76 → v1.0.77
- **日期**: 2026-04-22
- **现象**: 优选IP一两天不更新，永远是本地池的那几个IP
- **根因**: fetch_cdn_ips() 中本地池24个IP永远优先，只要前5个可达就停止，步骤2/3/4的外部API（WeTest.vip/001315/IPDB）永远不会被调用
- **修复**: 调整获取顺序为：WeTest.vip电信优选DNS（步骤1，实时获取）→ 001315电信API（步骤2，补充）→ IPDB API（步骤3，补充）→ 本地实测IP池（步骤4，兜底）
- **预防**: 外部API必须优先于本地固定池，确保每小时获取最新最快IP

### Bug #25: SOCKS5路由规则顺序错误导致X/推特/groK走错
- **版本**: v1.0.77 → v1.0.78
- **日期**: 2026-04-22
- **现象**: X/推特/groK 被AI规则匹配走了SOCKS5，而不是正常代理
- **根因**: subscription_service.py 和 config_generator.py 中，AI规则在X/推特/groK排除规则之前。sing-box按顺序匹配规则，先匹配到的生效，导致X/groK先被AI规则捕获走SOCKS5
- **修复**: 将X/推特/groK排除规则移到AI规则之前。客户端配置outbound改为ePS-Auto（走正常代理），服务端配置outbound为direct（VPS直连）
- **预防**: 排除规则必须放在被排除的规则之前，sing-box按顺序匹配

### Bug #26: SOCKS5缺少故障转移机制
- **版本**: v1.0.77 → v1.0.78
- **日期**: 2026-04-22
- **现象**: SOCKS5住宅代理挂了，AI网站完全无法访问
- **根因**: ai-residential selector 的 outbounds 只有 ["AI-SOCKS5"]，没有fallback选项
- **修复**: ai-residential selector 的 outbounds 改为 ["AI-SOCKS5", "direct"]，SOCKS5不可用时自动切直连
- **预防**: 所有selector必须包含fallback选项，防止单点故障

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

### Bug #28: AI规则包含google.com导致延迟测试走SOCKS5（360ms）
- **版本**: v1.0.80 → v1.0.82
- **日期**: 2026-04-23
- **现象**: v2rayN延迟测试显示170-193ms，但本地ping只有63ms；用户反馈"加了SOCKS5后延迟莫名其妙变高"
- **根因**: AI规则的domain_suffix包含了google.com/googleapis.com/gstatic.com。v2rayN延迟测试用www.google.com/generate_204，被AI规则匹配走了SOCKS5。延迟测到的是SOCKS5延迟（360ms）而非正常代理延迟（63ms+TLS开销）
- **修复**: 从AI规则中移除google.com/googleapis.com/gstatic.com。只保留AI专用子域名（gemini.google.com/bard.google.com/aistudio.google.com/ai.google）
- **预防**: AI规则中禁止包含通用域名（google.com等），只包含AI专用子域名。修改subscription_service.py时必须同步修改config_generator.py

### Bug #29: CDN优选IP返回104.x.x.x高延迟段（130ms+）
- **版本**: v1.0.82
- **日期**: 2026-04-23
- **现象**: CDN优选IP返回104.21.x.x/104.16-18.x.x段，对中国用户延迟130ms+，远高于162.159.x.x段的50ms
- **根因1**: WeTest.vip的DNS记录本身就是104段，即使用湖南电信DNS(222.246.129.80)或阿里DoH解析也返回104段。不是DNS服务器的问题，是WeTest.vip的Anycast分配问题
- **根因2**: 之前代码过滤104段后为空就"全部保留"，导致高延迟IP被使用
- **根因3**: 日本服务器无法直接dig中国内网DNS（超时），需要用DoH方式
- **修复**:
  1. CDN获取顺序改为：001315 API(返回173.245等优质段) → WeTest(104段严格过滤，为空就丢弃) → IPDB → 本地池(兜底)
  2. 过滤后为空就丢弃，不再"全部保留"
  3. 增加DoH支持（阿里DoH: dns.alidns.com），境外服务器也能解析
  4. `is_hunan_ct_optimal()`只允许162.159/172.64/108.162/198.41/173.245段
- **预防**: 
  - 104.x.x.x段必须严格过滤，不能"全部保留"
  - 001315 API优先（返回优质段），WeTest仅作补充
  - 境外服务器必须用DoH方式解析DNS，直接dig中国DNS会超时

### Bug #30: config_generator.py与subscription_service.py不同步
- **版本**: v1.0.82
- **日期**: 2026-04-23
- **现象**: 修改subscription_service.py的AI规则后，config_generator.py没有同步修改，导致服务端配置还是旧版本
- **根因**: 两个文件独立生成配置，修改一个忘了另一个
- **修复**: 同步修改config_generator.py的AI规则
- **预防**: 修改subscription_service.py时必须同步修改config_generator.py，两个文件都要更新。改A忘B=隐藏Bug

### Bug #31: CDN优选IP自动更新服务卡住
- **版本**: v1.0.82
- **日期**: 2026-04-24
- **现象**: CDN优选IP停在2026-04-23 22:18:35不再更新，过了24小时后还是同一套IP
- **根因**: singbox-cdn服务的 `time.sleep(3600)` 卡住，守护进程模式虽然显示active但不再执行后续更新
- **修复**:
  1. 手动运行CDN更新，IP已更换
  2. 重启singbox-cdn服务
  3. 添加crontab定时任务：每小时0分自动重启singbox-cdn，防止卡住
- **预防**: singbox-cdn服务必须有定时重启保障（每小时一次），防止time.sleep或其他原因导致服务挂住

### Bug #32: config_generator.py缺少DNS配置和final规则
- **版本**: v1.0.83
- **日期**: 2026-04-24
- **现象**: 服务端config.json的DNS服务器数=0，final为空，只有3条路由规则
- **根因**: config_generator.py从未添加DNS配置，final规则写成了普通规则而非route.final字段
- **修复**:
  1. 添加DNS配置（dns_proxy: tls://8.8.8.8 detour=direct, dns_direct: 223.5.5.5）
  2. 将 `{"outbound":"direct"}` 普通规则改为 `"final": "direct"`
- **预防**: config_generator.py生成的服务端配置必须包含DNS和final，与subscription_service.py的客户端配置保持结构一致

### Bug #33: S-UI旧面板残留进程和目录
- **版本**: v1.0.83
- **日期**: 2026-04-24
- **现象**: /opt/s-ui-manager/cdn_monitor.py还在运行，/usr/local/s-ui/sui进程还在，占用内存
- **根因**: install.sh的uninstall_old_panels只做了stop/disable，没有删除服务文件、目录和杀残留进程
- **修复**:
  1. 手动清理服务器上的S-UI残留（停止服务+删除服务文件+删除目录+杀进程）
  2. install.sh的uninstall_old_panels加强：删除所有相关systemd服务文件+删除安装目录+杀残留进程+daemon-reload
- **预防**: 卸载旧面板必须彻底：stop+disable+删除服务文件+删除目录+杀残留进程+daemon-reload

### Bug #34: CDN重启crontab未写入install.sh
- **版本**: v1.0.84
- **日期**: 2026-04-24
- **现象**: Bug #31修复时只在服务器上手动添加了crontab，但install.sh的setup_health_check_cron()没有写入，导致新服务器安装后CDN优选IP还是会卡住
- **根因**: 修复Bug #31时只在运行中的服务器上手动执行了crontab命令，忘记同步更新install.sh的安装脚本
- **修复**:
  1. install.sh的setup_health_check_cron()添加：每小时0分自动重启singbox-cdn
  2. 同时清理JSUI残留进程和目录
  3. 统一所有文件版本号为v1.0.84
- **预防**: 修复服务器问题时，必须同步更新install.sh安装脚本，确保新服务器安装也能获得同样的修复

### Bug #35: CDN本地IP池混入104.x.x.x高延迟段
- **版本**: v1.0.85
- **日期**: 2026-04-25
- **现象**: config.py的CDN_PREFERRED_IPS列表包含104.16.123.96/104.16.124.96/104.17.136.90三个104段IP，这些IP对中国用户延迟130ms+，违反了Bug #29自己制定的"104段严格过滤"规则
- **根因**: 本地IP池和外部API过滤逻辑是分开的。外部API获取的IP会经过is_hunan_ct_optimal()过滤，但本地硬编码的CDN_PREFERRED_IPS没有经过同样的过滤，导致104段IP"混"进了本地池
- **修复**:
  1. config.py: 移除3个104段IP，替换为162.159.36.1/172.64.35.78/162.159.40.55
  2. cdn_monitor.py: ImportError降级块中的CDN_PREFERRED_IPS同步更新
- **预防**: 本地IP池也必须遵守104.x.x.x过滤规则，不能因为"本地池"就放松标准。新增IP到CDN_PREFERRED_IPS时必须检查是否属于HUNAN_CT_OPTIMAL_PREFIXES

### Bug #36: cert_manager续签后漏重启singbox-cdn
- **版本**: v1.0.85
- **日期**: 2026-04-25
- **现象**: cert_manager.py证书续签后只重启singbox和singbox-sub，漏了singbox-cdn。CDN监控服务使用旧证书继续运行，可能导致HTTPS请求失败
- **根因**: Bug #15修复时只在tg_bot.py的update_env_and_restart()中添加了singbox-cdn重启，但cert_manager.py的restart_singbox()没有同步修改。两个文件各自独立调用重启命令，没有统一引用
- **修复**: cert_manager.py的restart_singbox()添加 `os.system('systemctl restart singbox-cdn')`
- **预防**: 服务重启必须覆盖所有相关服务（singbox + singbox-sub + singbox-cdn），无论在哪个文件中调用重启。建议将重启逻辑统一到config.py的一个函数中

### Bug #37: health_check漏检UDP端口（HY2/QUIC不可检测）
- **版本**: v1.0.85
- **日期**: 2026-04-25
- **现象**: health_check.sh的check_ports()只检查TCP端口，不检查UDP端口。Hysteria2使用QUIC协议（UDP 443），如果UDP 443未监听，HY2节点完全不可用，但健康检查不会报警
- **根因**: 初始实现时只考虑了TCP协议的端口检查，忽略了HY2使用UDP协议的特殊性
- **修复**: check_ports()增加UDP 443端口检查：`ss -ulnp | grep -q ":443 "`
- **预防**: 端口检查必须同时覆盖TCP和UDP，特别是HY2/QUIC协议使用UDP

### Bug #38: cdn_monitor数据库连接泄漏
- **版本**: v1.0.85
- **日期**: 2026-04-25
- **现象**: cdn_monitor.py的init_db()函数中，如果cursor.execute()或conn.commit()抛异常，数据库连接不会关闭，导致连接泄漏
- **根因**: conn.close()直接写在函数末尾，没有用try/finally包裹。违反了项目铁律#14"数据库连接必须在finally中关闭"
- **修复**: 将conn = sqlite3.connect()移入try块，conn = None兜底，finally中if conn防护关闭
- **预防**: 所有数据库连接必须在finally中关闭，即使init_db()这种简单函数也不能例外

### Bug #39: 414MB内存无Swap，OOM Killer杀掉进程导致掉线
- **版本**: v1.0.85
- **日期**: 2026-04-25
- **现象**: 服务器"时不时掉线突然连不上"，但ping正常。dmesg显示OOM killer已触发61次，杀掉了fwupd等进程。服务器只有414MB内存，无Swap分区
- **根因**: AWS t3.micro实例只有414MB内存，运行singbox(27MB)+subscription_service(36MB)+cdn_monitor(26MB)+系统服务后内存耗尽。fwupd服务占用144MB触发OOM，如果singbox进程被OOM杀掉就会导致"突然连不上"
- **修复**:
  1. 创建2GB Swap文件并写入/etc/fstab持久化
  2. 设置vm.swappiness=10（优先用物理内存，Swap做紧急缓冲）
  3. 禁用并mask fwupd.service（占用144MB且VPS不需要固件更新）
  4. 禁用snapd.service（节省24MB）
- **预防**: 小内存VPS（<1GB）必须配Swap（至少2GB），fwupd/snapd等不必要的服务必须禁用

### Bug #40: HUNAN_CT_OPTIMAL_PREFIXES包含未实测验证的IP段
- **版本**: v1.0.85
- **日期**: 2026-04-25
- **现象**: CDN优选IP数据库中出现8.39.125.x和8.35.211.x段IP，这些段不在用户实测数据中。001315 API返回这些IP但未经is_hunan_ct_optimal()过滤直接使用，导致非优质段IP进入CDN列表
- **根因**: 001315电信API返回8.39.x.x和8.35.x.x段IP，代码注释误标为"属于湖南电信最优段"，但用户实测数据（2026-04-25）显示优质段只有162.159/172.64/108.162/198.41/173.245。8.39/8.35段不在任何第三方CDN优选数据源中出现
- **修复**:
  1. HUNAN_CT_OPTIMAL_PREFIXES移除'8.39.'和'8.35.'前缀
  2. 001315 API返回的IP也必须经过is_hunan_ct_optimal()过滤
  3. CDN_PREFERRED_IPS用用户实测优质IP更新（前9个为实测排名）
- **预防**: CDN最优IP段必须以用户实测数据为准，API返回的IP段未经实测验证不能加入最优前缀列表

---

## Bug 修复历史

### Bug #9: AI-SOCKS5被错误地作为用户可见节点暴露
- **版本**: v1.0.48 → v1.0.49
- **日期**: 2026-04-21
- **现象**: 用户在V2rayN节点列表中看到"AI-SOCKS5"节点，首页HTML写着"包含6个节点"
- **根因**: AI实现SOCKS5功能时，只理解了"SOCKS5是个代理"的字面意思，把它当成普通节点塞进了Base64订阅链接和ePS-Auto selector。完全忽略了技术文档中"无感路由，用户无需手动选择"的设计意图
- **修复**:
  1. subscription_service.py: 移除generate_all_links()中的socks5://链接
  2. subscription_service.py: 移除ePS-Auto selector中的"AI-SOCKS5"选项
  3. subscription_service.py: 修复首页HTML从"6个节点"改为"5个节点"
  4. TECHNICAL_DOC.md: 明确AI-SOCKS5是幕后路由出站，不是用户可见节点
- **预防**: 规则11

### Bug #10: 跨文件配置不一致导致多处隐藏问题
- **版本**: v1.0.49 → v1.0.50
- **日期**: 2026-04-21
- **现象**: 全面审查发现13个隐藏问题：README把AI-SOCKS5列为节点、config_generator.py缺少AI路由域名和排除规则、tg_bot.py端口硬编码6969、设置住宅后不重启singbox-sub、SSL证书路径不一致、SOCKS5出站结构不一致、install.sh包名错误、文档版本过时、变量覆盖等
- **根因**: 
  - 多个文件独立实现相同功能，没有统一引用config.py作为唯一真相源
  - 修改一个文件时没有全局搜索所有引用该配置的文件（违反规则9）
  - 新增功能时只在subscription_service.py实现，没有同步更新config_generator.py
  - 文档更新不彻底（违反规则10）
- **修复**: 详见project_snapshot.md v1.0.50更新内容
- **预防**: 规则12

### Bug #12: 证书文件名不一致导致续签和检查形同虚设
- **版本**: v1.0.51 → v1.0.52
- **日期**: 2026-04-21
- **现象**: 证书7月19日到期后不会自动续签；cert_manager.py检查的cert.crt根本不存在
- **根因**: 
  - cert_manager.py生成cert.crt+cert.key，但config_generator.py引用cert.pem+key.pem，两套文件名
  - check_cert_expiry()只检查cert.crt，服务器实际用的是fullchain.pem+key.pem（acme.sh）和cert.pem+key.pem（Cloudflare API）
  - 没有配置证书续签cron定时任务
  - health_check.sh只检查fullchain.pem，漏检cert.pem
- **修复**: 
  1. cert_manager.py: CERT_FILE从cert.crt改为cert.pem，KEY_FILE从cert.key改为key.pem
  2. check_cert_expiry(): 循环检查fullchain.pem和cert.pem，找到哪个用哪个
  3. health_check.sh: 同样兼容fullchain.pem和cert.pem
  4. install.sh: 添加证书续签cron（每月1号凌晨3点执行cert_manager.py --renew）
  5. 服务器: 手动添加cert_manager.py续签cron
- **预防**: 证书文件名必须统一为cert.pem+key.pem（与config_generator.py一致），续签必须有cron保障

### Bug #13: install.sh防火墙全放行清除端口跳跃规则
- **版本**: v1.0.48 → v1.0.52
- **日期**: 2026-04-21
- **现象**: 新VPS安装后HY2端口跳跃不工作
- **根因**: install.sh中setup_firewall()在setup_port_hopping()之后执行，iptables -F清空了所有规则包括刚设置的端口跳跃规则
- **修复**: 调整执行顺序，setup_firewall移到setup_port_hopping之前
- **预防**: 防火墙重置必须在iptables规则设置之前

### Bug #14: tg_bot.py运行CDN更新会死循环
- **版本**: v1.0.52
- **日期**: 2026-04-21
- **现象**: TG机器人/优选命令执行后永远无响应
- **根因**: update_cdn()用subprocess.run运行cdn_monitor.py，但cdn_monitor.py是while True无限循环，永远不会退出
- **修复**: 改为直接import cdn_monitor的fetch_cdn_ips和assign_and_save_ips函数，只执行一次
- **预防**: 调用长期运行脚本时必须区分"单次执行"和"守护进程"模式

### Bug #15: tg_bot.py设置住宅后不重启singbox-cdn
- **版本**: v1.0.52
- **日期**: 2026-04-21
- **现象**: 设置AI住宅IP后CDN监控服务不刷新
- **根因**: update_env_and_restart()只重启singbox和singbox-sub，漏了singbox-cdn（违反铁律11）
- **修复**: 添加systemctl restart singbox-cdn
- **预防**: 服务重启必须覆盖所有相关服务：singbox + singbox-sub + singbox-cdn

### Bug #16: subscription_service.py硬编码覆盖config.py的HYSTERIA2_UDP_PORTS
- **版本**: v1.0.52
- **日期**: 2026-04-21
- **现象**: HY2端口范围定义不统一，违反唯一真相源原则
- **根因**: subscription_service.py第55行 HYSTERIA2_UDP_PORTS = list(range(21000, 21201)) 覆盖了从config.py导入的同名变量
- **修复**: 删除该行，直接使用config.py导入的值
- **预防**: 配置值只在config.py定义，其他文件必须import，禁止各自独立定义（规则4）

### Bug #11: HY2端口跳跃iptables规则端口范围错误+缺少TCP规则
- **版本**: v1.0.50部署时
- **日期**: 2026-04-21
- **现象**: HY2不通，客户端无法连接Hysteria2节点
- **根因**: 
  - 服务器iptables规则是旧的22000:22200范围，但config.py和订阅链接生成的是21000-21200
  - 只有UDP规则没有TCP规则（违反铁律：HY2必须UDP+TCP双规则）
  - 上传代码时没有同步运行cert_manager.py重新生成iptables规则
- **修复**: 
  1. 清空旧iptables PREROUTING规则
  2. 重新生成21000-21200范围的UDP+TCP双协议DNAT规则（共402条）
  3. netfilter-persistent save持久化
- **预防**: 部署代码后必须运行cert_manager.py或手动检查iptables规则是否与config.py一致

### Bug #8: HY2端口跳跃目标端口错误（4433→443）
- **版本**: v1.0.44 → v1.0.45
- **日期**: 2026-04-21
- **现象**: Hysteria2端口跳跃功能无效，客户端使用21000-21200端口无法连接
- **根因**: cert_manager.py将21000-21200端口DNAT到4433，但singbox配置中HY2监听443端口。端口跳跃流量到达4433但无服务监听
- **修复**: 
  1. cert_manager.py: DNAT目标从4433改为443
  2. 移除TCP规则（HY2只用UDP）
  3. subscription_service.py: mport从22000-22200统一为21000-21200
  4. config.py: 新增HY2规避配置说明注释
- **预防**: 规则8和规则9

### Bug #7: 代码硬编码导致新VPS部署困难
- **版本**: v1.0.44 → v1.0.45
- **日期**: 2026-04-21
- **现象**: 新VPS部署时需手动修改大量硬编码的IP、域名、凭据、路径
- **根因**: 开发过程中为图方便硬编码了各种配置值
- **修复**: 
  1. config.py: 新增_detect_server_ip()自动检测IP，新增_load_env_value()统一读取.env
  2. subscription_service.py: 所有硬编码改为动态读取，SOCKS5凭据改为环境变量
  3. config_generator.py: 所有硬编码路径改为从BASE_DIR/CERT_DIR拼接
  4. cert_manager.py: .env路径改为从BASE_DIR拼接
  5. 清理26个临时脚本（含硬编码凭据）
- **预防**: 规则6

### Bug #6: CDN优选IP获取方式不正确
- **版本**: v1.0.44 → v1.0.45
- **日期**: 2026-04-21
- **现象**: CDN优选IP使用固定IP池+随机ping，IP可能过期失效
- **根因**: 未使用指定的DNS服务器解析
- **修复**: cdn_monitor.py改为三层获取策略：指定DNS→降级DNS→固定IP池
- **预防**: 规则7

### Bug #5: V2rayN无法更新订阅（证书域名不匹配）
- **版本**: v1.0.43 → v1.0.44
- **日期**: 2026-04-21
- **现象**: V2rayN更新订阅（IP地址访问HTTPS）失败
- **根因**: SSL证书颁发给域名，用IP访问时证书域名不匹配，V2rayN拒绝连接。9443端口不在CDN代理列表中，无法通过域名走CDN
- **修复**: SUB_PORT 9443→2087（CDN支持端口），订阅URL改为域名访问
- **验证**: Windows本地curl（不跳过验证）返回200 OK，证书匹配
- **预防**: 规则1和规则2

### Bug #4: 订阅端口9443从外部无法访问
- **版本**: v1.0.41 → v1.0.42
- **日期**: 2026-04-21
- **现象**: 订阅链接从外部无法访问，端口超时
- **根因**: 三重bug叠加——代码默认端口6969、防火墙只放行6969、CDN不代理9443
- **修复**: 默认端口6969→9443、iptables放行9443、path编码一致性
- **遗留问题**: 9443不在CDN支持列表中，导致Bug #5
- **预防**: 规则3

### Bug #3: Trojan-WS协议不通
- **版本**: v1.0.40 → v1.0.41
- **日期**: 2026-04-20
- **现象**: Trojan-WS节点无法连接
- **根因**: 缺少SSL配置 + path参数URL编码不一致
- **修复**: 添加SSL配置 + 统一使用 `urllib.parse.quote(str(v), safe='')`
- **预防**: 规则9

### Bug #2: CDN优选IP对中国用户延迟高
- **版本**: v1.0.36 → v1.0.37
- **日期**: 2026-04-20
- **现象**: 从日本服务器DNS解析获取的CDN IP对中国用户延迟高
- **根因**: 日本服务器解析的CDN IP对中国不友好
- **修复**: 恢复固定优选IP池（中国用户实测50ms左右）
- **预防**: 规则7

### Bug #1: Trojan-WS链接缺少insecure=1参数
- **版本**: v1.0.38 → v1.0.39
- **日期**: 2026-04-20
- **现象**: Trojan-WS链接在某些客户端无法使用
- **根因**: 缺少allowInsecure=1参数
- **修复**: 添加 insecure=1 和 allowInsecure=1 参数