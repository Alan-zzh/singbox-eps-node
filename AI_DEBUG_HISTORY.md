# AI 调试历史与防Bug规则 (AI Debug History)

## 最新排查（2026-05-31）

### Clash 极致性能压榨与爱快保活调优 [OpenCode]
- **现象**: 用户在自动选择和正常使用下，遇到断连和卡顿。
- **根因**: 
  1. 爱快（iKuai）路由器等普通 NAT 路由器的连接追踪表会将无流量的连接在 63 秒内过期剔除，导致后台连接（如推特 DM / WebSockets）无感中断，随后的回包由于无端口映射直接被丢弃（表现为 40% 丢包率）。
  2. Clash DNS 的 nameserver 错误配置为 Google/Cloudflare DOH（已被国内屏蔽/强污染），在解析国内直连流量时产生长达数秒的超时延迟，严重拖慢整体浏览体验。
  3. 电信用户的国际 IPv6 路由极其劣质，若开启 IPv6 会触发路由黑洞导致卡死。
- **修复**:
  1. 新增 `keep-alive-interval: 15`（15s 物理保活包），解决爱快路由器 63s 硬件断连暗刺。
  2. nameserver 改用国内阿里/腾讯近源 DNS（支持 DOH），国内页面直接秒开。
  3. 增加 `default-nameserver` 避免 DOH 自解析死锁，设置 `ipv6: false` 规避路由黑洞。
  4. 开启 `tcp-concurrent: true` 并发，`unified-delay: true` 测量精准可用延迟。
- **教训**: 
  1. 必须根据用户的本地网络设备特征（如 iKuai NAT）专门加入物理保活参数。
  2. nameserver 不能硬套国外安全 DNS，国内流量解析必须用最快的本地近源 DNS 组合，国外流量则通过 fake-ip 委托远端代理节点解析。

## 最新排查（2026-05-30）

### Clash MATCH 规则指向 url-test 导致手动选择无效 [OpenCode]
- **现象**: 用户 Clash 切到"手动选择"模式，发消息仍然失败；Clash 日志显示一直在自动切换节点
- **根因**: Clash 订阅生成的 `rules` 中 `MATCH` 指向 `{CC}-自动选择`（url-test 组），`{CC}-手动选择`（select 组）虽然存在但没有任何规则引用它。用户在 UI 里无论怎么选节点，流量始终被 MATCH 规则强制送入 url-test 组，导致自动切换永不停止
- **修复**: 
  1. `手动选择` 重命名为 `节点选择`（select 组），作为唯一入口
  2. `节点选择` 的 proxies 包含 `{CC}-自动选择` 作为第一个选项 + 所有单个节点
  3. `MATCH` 从 `{CC}-自动选择` 改为 `{CC}-节点选择`
  4. 用户选"JP-自动选择"→ 走 url-test；选"JP-VLESS-Reality"→ 固定节点
- **教训**:
  1. Clash 的 MATCH 规则必须指向 select 组，不能指向 url-test 组
  2. select 组必须包含 url-test 组作为一个选项 + 所有单节点
  3. "用户手动选择"在 Clash 规则层面必须显式设置，否则 UI 的点击无实际效果

### Clash url-test 参数优化与 failover 避险 [OpenCode]
- **现象**: 用户在自动选择下，发消息或上传大文件频繁失败，手动点选 CDN 节点却完全正常。
- **根因**: 
  1. 我们在 `v4.10.9` 将 `interval` 改为了 600（10分钟），且设为 `lazy: true`（懒加载）。
  2. 我们的 Reality（直连）节点丢包高达 20-40%，但基础延迟低。
  3. 当 Clash 第一次测速成功通过 Reality 后，会因为其延迟低于 CDN 节点，立马将其设为默认。
  4. 随后，即便 Reality 开始大量丢包导致网页卡死或消息发送失败，由于容差设为了 150ms 且测速间隔长达 10 分钟，Clash 无法在短时间内重新测速并切换到健康的 CDN 节点，直接将用户流量锁死在坏节点上。
  5. 之前以为测速连接的 "mux EOF" 是 Bug #88 频繁断连，其实那是正常的测速断开日志（无害）。
- **修复**:
  1. 将自动测速组配置改为：`interval: 60`（1分钟高灵敏度检测故障）、`tolerance: 150`（150ms高容差防止日常波动乱切换）、`lazy: false`（后台常态化测速，确保最新健康状态）。
  2. 测速源使用 `http://cp.cloudflare.com/generate_204`，避免 TLS 握手损耗。
  3. 通过这组“黄金参数组合”（60s间隔 + 150ms容差），完美兼顾了“防乱切”与“快速避险”。
- **教训**: 
  1. url-test 在遇到高丢包线路时，不能用太长的测速间隔，否则一旦锁死坏节点会造成灾难性的长时间断连。
  2. 必须用高容差（如 150ms）来防波动，而不是用超长测速间隔（600s）来防切换。
  3. 测速源使用 HTTP 协议（非 HTTPS）能提供更稳定、轻量的测试环境，是商业机场的标准实践。

### v4.10.4/v4.10.5 修复未部署到服务器 [OpenCode]
- **现象**: JP/SG 服务器 `/api/cdn-status` 返回 500（`name '_health_monitor' is not defined`），subscription_service 日志报 `UnicodeEncodeError`
- **根因**: v4.10.4（global→nonlocal）和 v4.10.5（charset=utf-8）的修复代码在本地改了但从未上传到远端服务器。JP 和 SG 服务器上的 subscription_service.py 仍为旧代码
- **修复**: 
  1. 本地 subscription_service.py 确认 `global→nonlocal` 修复（L2158）
  2. charset=utf-8 已在本地（L1871/L1896）确认存在
  3. 通过 SFTP 同时部署到 JP + SG 服务器
  4. 重启 singbox-sub 并验证 `/api/cdn-status` 返回 200
- **教训**: 代码修复后必须立即部署到所有线上服务器，不能只改本地不推送。修复清单与部署清单必须对应。建议每次发布前用 `diff` 对比本地和线上版本。

### 开启DEBUG日志监控CDN优选 [TRAE SOLO CN]
- **需求**: 用户要求监控接下来10次CDN优选探测的详细日志
- **操作**: 修改logger.py和cdn_monitor.py，把日志级别从INFO改为DEBUG
- **验证**: SG服务器已看到DEBUG级别的日志输出

### probe_user_network TCP 443不通误判NAT [TRAE SOLO CN]
- **现象**: probe_user_network() TCP 443连不上用户IP就判定NAT跳过所有测试，但用户IP 175.10.213.63 ICMP ping完全通（70ms）
- **根因**: 用户是普通宽带，不开443端口，但ICMP是通的。代码只测TCP 443，不通就跳过
- **修复**: TCP 443不通时尝试ICMP ping（ping -c 5），ICMP通则用ICMP结果作为延时和丢包依据；ICMP也不通才用CDN回源测速
- **教训**: 用户IP可达性检测不能只看TCP端口，ICMP ping是更基础的可达性判断

### 三网均衡度前缀表覆盖太窄 [TRAE SOLO CN]
- **现象**: calculate_cross_isp_score() 对几乎所有IP返回50（中性），三网均衡度无区分度
- **根因**: THREE_ISP_OPTIMAL_PREFIXES只列了极少数Cloudflare子段，当前IP池里的IP（162.159.x.x, 172.64.x.x, 104.18.x.x）几乎都不在表里
- **修复**: 新增三网API IP缓存机制（_three_isp_cache），fetch_cdn_ips()时同时获取三网各自API的IP列表缓存，calculate_cross_isp_score()优先查缓存判断IP在哪些ISP优质列表中出现，前缀表降级为备选
- **教训**: Cloudflare IP段不按运营商分配，前缀匹配不可靠，必须用实际API数据判断

### CDN优选评分不含用户路径和三网均衡度 [TRAE SOLO CN]
- **现象**: CDN优选评分只看VPS→CDN延迟+速度+稳定性(40+30+30)，用户路径测速和三网匹配代码存在但未激活
- **根因**: v4.10简化评分算法时移除了用户路径和ISP匹配权重，`calculate_composite_score()` 接收 `isp_type` 参数但未使用；`user_isp_match` 和 `composite_score_v2` 数据库字段全为0
- **修复**: 评分算法改为双模式：用户路径可用时 VPS延迟(15%)+VPS速度(15%)+用户路径延迟(25%)+用户路径速度(25%)+三网均衡(15%)+稳定性(5%)；不可用时降级为 VPS延迟(25%)+VPS速度(25%)+三网均衡(30%)+稳定性(20%)。三网均衡权重：电信×0.45+联通×0.35+移动×0.20
- **教训**: 评分算法必须包含端到端质量维度，仅看VPS侧不够

### VPS→用户IP直连测试NAT误判 [TRAE SOLO CN]
- **现象**: `probe_user_network()` 测VPS→用户IP(zzpzgroup.com)的TCP/HTTP连通性，但用户在NAT后面，VPS连不上用户443端口，导致延时9999ms/丢包100%
- **根因**: VPS无法主动连接NAT后的用户IP，直连测试必然失败
- **修复**: 先单次TCP试探判断NAT，NAT环境跳过直连测试，改用CDN回源测速代替；质量判断NAT环境用CDN回源延时（阈值×3）
- **教训**: VPS→用户直连测试在NAT环境下无意义，必须用CDN回源测速代替

### CDN优选系统TCP检测全部误判：cdn_ips_list JSON格式不兼容 [TRAE SOLO CN]
- **现象**: JP 280次/SG 320次 "TCP死亡"，0次"TCP存活"，但手动测试5个IP全部存活
- **根因**: v4.10.2将 `cdn_ips_list` 写入格式从逗号分隔改为JSON数组 `[{"ip":"1.2.3.4","score":75},...]`，但 `get_current_cdn_ips_from_db()` 仍用 `split(',')` 解析，导致解析出非法字符串如 `[{"ip":"1.2.3.4"`，socket.connect_ex()必然抛异常返回False
- **受影响位置**: cdn_monitor.py L1693（1处）+ subscription_service.py L130/L2051/L2166（3处），共4处 `split(',')` 需修复
- **修复**: 所有读取位置判断值是否以 `[` 开头，是则 `json.loads()` 提取ip字段，否则逗号分割；subscription_service.py 提取公共函数 `parse_cdn_ips_list()` 避免重复
- **教训**: 数据格式变更时必须同步所有读取端，否则写入和读取不一致会导致隐蔽bug

### Clash订阅配置UnicodeEncodeError：Response未指定charset [TRAE SOLO CN]
- **现象**: SG服务器10次 `UnicodeEncodeError: 'latin-1' codec can't encode characters in position 42-46`
- **根因**: Clash配置含中文节点名（"自动选择"/"手动选择"），Singbox配置用 `ensure_ascii=False`，但Response的mimetype未指定charset，Werkzeug在WSGI层面可能用非UTF-8编码
- **修复**: Clash Response `mimetype='text/plain'` → `text/plain; charset=utf-8`；Singbox Response `application/json` → `application/json; charset=utf-8`
- **教训**: HTTP Response返回含非ASCII字符时必须显式指定charset=utf-8

## 最新排查（2026-05-29）

### /api/cdn-status 500错误：_health_monitor作用域bug [TRAE SOLO CN]
- **现象**: 两台服务器 `/api/cdn-status` 返回500，错误 `name '_health_monitor' is not defined`
- **根因**: `_health_monitor` 和 `_failover_controller` 定义在 `create_app()` 函数内部（L2135-2136），但 `cdn_status_api()` 使用 `global` 声明引用。Python的 `global` 指向模块级作用域，不是外层函数作用域，导致 NameError
- **修复**: `global _failover_controller, _health_monitor` → `nonlocal _failover_controller, _health_monitor`
- **教训**: Python中变量定义在函数内部时，内嵌函数要用 `nonlocal` 而非 `global` 引用；`global` 只指向模块级

### JP服务器HY2连接127.0.0.1:5151被拒绝（42万+次） [TRAE SOLO CN]
- **现象**: JP服务器singbox.log有423,282条 `connection to 127.0.0.1:5151: connection refused` 错误，日志膨胀到374MB
- **根因**: 客户端TUN模式将本地SOCKS5代理连接(127.0.0.1:5151)捕获并路由到代理隧道，服务端收到后尝试直连127.0.0.1:5151失败。服务端路由规则为空（`rules: []`），所有流量走direct，包括私有地址
- **修复**: config_generator.py服务端路由规则最前面添加私有地址拒绝规则（127.0.0.0/8等→block），阻止客户端代理请求连接私有地址
- **教训**: 服务端必须拦截私有地址代理请求，否则客户端TUN模式会将本地连接泄漏到代理隧道

### JP服务器缺少logrotate，日志374MB [TRAE SOLO CN]
- **现象**: JP服务器singbox.log达374MB，无logrotate配置；SG服务器正常（2.5MB，有logrotate）
- **根因**: JP服务器部署时未执行logrotate配置步骤
- **修复**: 部署 `/etc/logrotate.d/singbox` 配置（daily, rotate 7, maxsize 50M），清理374MB日志
- **教训**: 部署后必须验证logrotate配置存在

## 最新排查（2026-05-28）

### cdn_quality_filter.py 评分权重总和不等于1 [TRAE SOLO CN]
- **现象**: 八维评分权重总和 0.07+0.07+0.12+0.10+0.04+0.10+0.18+0.17+0.15 = 1.01，超出了1.0，导致最终分数最高可达 101 分
- **修复**: 将 `cross_isp` 权重从 0.15 调整为 0.14，使总和刚好等于 1.0

### v4.10.2 高延迟IP被分配给用户（104.16.148.7延迟高却进了订阅） [TRAE SOLO CN]
- **现象**: 104.16.148.7延迟很高，却被分配给Trojan-WS协议写入订阅
- **根因**: fetch_cdn_ips()步骤4中 `final_ips = list(alive_ips)`，只要IP"活着"就无脑保留，不管延迟多高评分多低。当alive_ips已经够CDN_TOP_IPS_COUNT(5)个时，fill_needed=0，评分更好的候选IP完全没机会替换进来。存活≠质量好
- **次要根因**: assign_and_save_ips()从Top5里random.sample选3个，评分第1和第5被选中概率一样；cdn_ips_list存逗号分隔字符串不含评分，订阅服务换IP时随机选
- **修复**:
  1. 步骤4改为从tested_results（已评分排序）中取Top CDN_TOP_IPS_COUNT个，不再无脑保留存活IP
  2. assign_and_save_ips()按评分排序直接取前3名分配，不再随机
  3. cdn_ips_list改为JSON格式（含评分+延迟），订阅服务换IP时按评分选最高分的
- **教训**: "存活"不等于"质量好"，筛选逻辑必须基于评分而非存活状态

### v4.10.1 订阅服务不返回优选IP，仍用原始CF域名 [TRAE SOLO CN]
- **现象**: cdn_monitor已将优选IP写入数据库，但订阅服务返回的CDN节点地址仍是jp.290372913.xyz/sg.290372913.xyz原始域名
- **根因**:
  1. 订阅服务(subscription_service.py)是长驻Flask进程，从5月27日就在跑，没重启过
  2. cdn_monitor写入数据库后，订阅服务进程没有感知机制，缓存不刷新
  3. get_cdn_ip_for_protocol()有_cdn_ip_cache（10分钟TTL），但主要问题是进程启动时DB里没有优选IP，后续DB更新了进程也不知道
- **修复**:
  1. cdn_monitor的assign_and_save_ips()末尾写入信号文件data/.cdn_ip_updated
  2. subscription_service的get_cdn_ip_for_protocol()开头检查信号文件，存在则清空缓存
  3. 重启两台服务器订阅服务进程
- **教训**: 长驻进程必须有数据变更感知机制，不能指望手动重启；信号文件是最轻量的跨进程通知方式

### USER_DDNS_DOMAIN读不到.env文件 [TRAE SOLO CN]
- **现象**: 服务器.env有USER_DDNS_DOMAIN=zzpzgroup.com，但cdn_monitor日志显示"DDNS域名未配置"
- **根因**: config.py中USER_DDNS_DOMAIN = os.getenv('USER_DDNS_DOMAIN', '').strip()，os.getenv()只读系统环境变量，不会自动读.env文件
- **修复**: 改为 USER_DDNS_DOMAIN = os.getenv('USER_DDNS_DOMAIN', '') or _load_env_value('USER_DDNS_DOMAIN', '')，双重读取
- **教训**: config.py中其他用os.getenv()读取的配置项也可能有同样问题，需要统一用双重读取模式

### v4.9五维评分3个维度无效，v4.10简化修复 [TRAE SOLO CN]
- **现象**: CDN优选IP评分区分度差（JP 64-66分，SG 49-55分），用户端延迟大、速度0
- **根因**:
  1. CDN→Google测速始终返回0（test_google_path_latency有bug），五维评分中20%维度白算
  2. ISP匹配度全是50分（USER_DDNS_DOMAIN未配置时detect_user_isp返回unknown，calculate_isp_match_score默认50），35%维度中15%无区分度
  3. 大量IP速度=0（health_check阶段没做速度测试或超时），10%维度白算
  4. 实际只有VPS→CDN延迟(25%)和稳定性(10%)在工作，有效维度仅35%
  5. 104.16/104.17段IP不应在获取时强制过滤，应通过测速自然淘汰
- **修复**: v4.10简化为3维评分：VPS→CDN延迟(40%)+速度(30%)+稳定性(30%)
- **教训**: 评分维度必须全部有效，无效维度等于白算且拉低区分度；获取IP时不应强制过滤IP段

### CDN→Google测速不影响用户体验 [TRAE SOLO CN]
- **现象**: v4.9新增CDN→Google测速，但数据库中所有IP的google_latency_ms=0, google_speed_mbps=0
- **根因**: 用户真实体验链路=用户→CDN→服务器，CDN→Google这段跟用户没关系
- **修复**: v4.10移除CDN→Google测速，不参与评分
- **教训**: 服务器测的延迟≠用户体验，但完整链路=用户域名→CDN+CDN→服务器，不要多加无关维度

### 104段IP强制过滤是错误的 [TRAE SOLO CN]
- **现象**: v4.10初版在fetch_isp_matched_ips中强制过滤104.16/104.17/104.19段IP
- **根因**: 三网API返回的数据就是要更完善的，不应该在获取时就过滤，应先全部获取→测速筛选→反复不好的再淘汰
- **修复**: 移除强制过滤，只做去重，通过测速评分自然淘汰
- **教训**: 获取IP时不应预判好坏，让测速数据说话

## 最新排查（2026-05-27）

### CDN优选IP误判为失效 [TRAE SOLO CN]
- **现象**: CDN节点全部崩溃，两台服务器CDN连接失败
- **误判过程**: 用 `curl -H 'Host: 域名' IP:端口` 测试返回000，误认为Cloudflare SNI严格验证拒绝IP直连
- **真相**: `-H 'Host'` 只改HTTP头，TLS Client Hello中SNI仍是IP地址，Cloudflare拒绝的是"无SNI"连接
- **验证**: `curl --resolve '域名:端口:IP'` → 404成功；`openssl -servername 域名 IP:端口` → TLS握手成功
- **教训**: 测试CDN IP连通性必须用 `--resolve` 或 `openssl -servername`，不能用 `-H 'Host'`
- **修复**: v4.7先回退域名模式止血，v4.8纠正误判恢复优选IP+新增三模式配置

### cdn_monitor.py 数据库路径重复拼接 [TRAE SOLO CN]
- **现象**: `fetch_cdn_ips()` 中 `db_path_check` 重复拼接 `os.path.join(DATA_DIR, 'singbox.db')`，而 `db_path` 已经是 `init_db()` 返回的完整数据库路径
- **根因**: `init_db()` 内部已拼接过一次完整路径并返回，但调用处又重复拼接了一次，导致打开的可能是一个错位数据库，评分计算始终为 0，可能误触发不必要的 CDN 刷新
- **修复**: 直接使用已有的 `db_path` 替代重复构造的 `db_path_check`

### health_monitor.py 状态文件路径优化 [TRAE SOLO CN]
- **现象**: 状态文件存储在 `/tmp/` 目录，系统重启后会丢失，导致报警计数重置
- **修复**: 将状态文件路径改为 `data/` 目录，并自动创建目录（如果不存在）
- **改动**: `STATE_FILE = '/tmp/singbox_monitor_state.json'` → `STATE_FILE = os.path.join(DATA_DIR, 'singbox_monitor_state.json')`

### subscription_service.py 重复导入修复 [TRAE SOLO CN]
- **现象**: 在函数内部重复导入 `CDN_IP_HARD_REJECT`，该配置已在文件顶部导入
- **修复**: 
  1. 在顶部导入语句中添加 `CDN_IP_HARD_REJECT`
  2. 在降级代码块中添加默认值 `CDN_IP_HARD_REJECT = {'latency_ms': 500, 'packet_loss_rate': 0.3, 'download_speed_mbps': 5}`
  3. 删除函数内的 `try/except ImportError` 块和重复导入语句
- **教训**: 避免在函数内部重复导入模块，应在文件顶部统一导入

### cdn_monitor.py calculate_composite_score() 参数缺失修复 [TRAE SOLO CN]
- **现象**: `calculate_composite_score()` 函数调用缺少 `user_probe_result` 参数，虽然有默认值但无法使用 v4.5 的完整评分功能
- **根因**: 有三个地方调用时没有传入该参数：第 1179 行（平均评分检查）、第 1451 行（assign_and_save_ips）、第 1530 行（health_check）
- **修复**: 
  1. `fetch_cdn_ips()` 中获取 `user_probe_result` 并在调用时传入
  2. `assign_and_save_ips()` 函数签名添加 `user_probe_result=None` 参数
  3. `fetch_cdn_ips()` 返回值改为 `(final_ips, user_probe_result)`
  4. `run_once()` 接收两个返回值并传递给 `assign_and_save_ips()`
  5. `health_check()` 中获取 `user_probe_result` 并在调用时传入
- **教训**: 修改函数签名后必须检查所有调用位置并同步更新

### health_monitor.py KeyError 修复 [TRAE SOLO CN]
- **现象**: 访问不存在的字典键 `info['status']` 导致 KeyError，监控脚本崩溃
- **根因**: `check_service()` 函数返回的字典中没有 `status` 键，只定义了 `active`、`restarts`、`port_ok`、`time` 键
- **修复**: 在 `check_service()` 函数的返回字典中新增 `'status': 'active' if active else 'inactive'` 字段
- **教训**: 修改打印语句前必须先检查对应键是否在数据结构中存在

## 最新排查（2026-05-26）

### VLESS-HTTPUpgrade Clash 不兼容修复 [Trae CN]
- **现象**: Clash Verge 中 `JP-VLESS-HTTPUpgrade` / `SG-VLESS-HTTPUpgrade` 节点连不上
- **排查**: 对比 Clash Meta 官方传输层文档发现 `network: httpupgrade` 不是合法值。Clash Meta 只支持 `http/h2/grpc/ws/xhttp` 五种传输层。sing-box 的 `httpupgrade` 传输是私有协议，Clash 需要通过 `ws-opts.v2ray-http-upgrade: true` 模拟
- **根因**: subscription_service.py L1416-L1433 中 Clash 配置使用了错误的字段：`network: "httpupgrade"` + `httpupgrade-opts`，这两个字段 Clash Meta 都不识别，导致节点配置被静默丢弃
- **修复**: 将 network 改为 `"ws"`，将 `httpupgrade-opts` 改为 `ws-opts`，并在 ws-opts 中添加 `v2ray-http-upgrade: true`
- **验证**: 服务端直接调用 `generate_clash_config()` 验证输出包含正确字段 `{"network": "ws", "ws-opts": {"path": "/vless-upgrade", "headers": {"Host": "..."}, "v2ray-http-upgrade": true}}`
- **教训**: Clash Meta 与 sing-box 的传输层命名规则不一致。sing-box 的 `httpupgrade` 在 Clash 中必须用 `ws` + `v2ray-http-upgrade` 模拟。新增任何 Clash 协议前必须先查 Meta 官方传输层文档

## 最新排查（2026-05-25）

### pkill 自杀导致 singbox-sub 永远无法启动 [Trae CN]
- **现象**: 添加 ExecStartPre 端口清理逻辑后，singbox-sub 一直 activating，重启 NRestarts 持续增长
- **排查**: journalctl 显示 `Control process exited, code=killed, status=9/KILL`，ExecStartPre 进程被杀掉
- **根因**: `ExecStartPre=/bin/bash -c 'pkill -9 -f "subscription_service.py"'` 中，pkill 自己的命令行包含 "subscription_service.py"，导致 **pkill 匹配到自己的进程并把自己杀掉**（signal 9/KILL）。这是 pkill 的经典自杀陷阱
- **修复**: 
  1. 改用 `fuser -k 2087/tcp` 精确杀掉占用端口的进程（fuser 命令行不包含服务名）
  2. ExecStartPre 改为: `/bin/bash -c 'PID=$(fuser -k 2087/tcp 2>/dev/null) && [ -n "$PID" ] && echo "清理端口占用 PID=$PID" || true'`
  3. health_monitor.py 中用 `ps aux | grep | awk` + `kill -9` 方式清理，没有 pkill 自杀风险
- **教训**: **绝对不要在 ExecStartPre 中使用 `pkill -f "服务名.py"`**，因为 pkill 会匹配到自己的命令行。改用 `fuser -k 端口/tcp` 或手动 ps+kill

### nohup 幽灵进程占用端口导致 systemd 服务重启 18861 次 [Trae CN]
- **现象**: 新加坡节点非常卡，更新订阅后 tcp_keep_alive/connect_timeout 未生效
- **排查**: SSH 发现两个进程同时运行 subscription_service.py：
  1. PID 246979/246980：`nohup python3 scripts/subscription_service.py`（5月24日18:32启动，占着端口2087）
  2. systemd `singbox-sub` 服务：一直启动失败（端口被占），重启了 18861 次
- **根因**: 早期用 nohup 方式启动过服务，后来迁移到 systemd，但没有杀掉旧进程。systemd 重启时端口被旧进程占用，永远无法绑定成功，形成"重启-失败-再重启"的死循环
- **修复**: 
  1. 在 singbox-sub.service 中加入 `ExecStartPre=/bin/bash -c 'pkill -9 -f "subscription_service.py" 2>/dev/null || true'`
  2. 加入 `ExecStartPre=/bin/sleep 2` 等待端口释放
  3. 创建 health_monitor.py 服务健康监控脚本，每 5 分钟检查服务状态 + 自动清理残留进程
  4. 创建 singbox-monitor.service 开机自启监控
  5. 支持邮件报警（SMTP 配置）
- **教训**: 任何服务迁移启动方式时，必须先清理旧进程；systemd 服务必须加 ExecStartPre 清理逻辑防止端口冲突；服务启动失败超过阈值必须报警

### cdn_monitor.py 硬编码 SG 端口 2085 [Trae CN]
- **现象**: 新加坡服务器 443/8443/2053/2083 端口监听失败
- **根因**: cdn_monitor.py 中硬编码 SUB_PORT=2085（日本服务器端口），不读取 .env
- **修复**: 所有端口读取改为从 .env / 环境变量获取，不再硬编码
- **教训**: 禁止在脚本中硬编码任何端口/配置，统一从 .env 或 config.py 读取

## 最新排查（2026-05-24）

### idle_timeout 导致 sing-box FATAL 崩溃 [TRAE SOLO CN]
- **现象**: v2rayN 更新订阅后所有节点连不上，sing-box 持续重启 160+ 次
- **报错**: `inbounds[1].idle_timeout: json: unknown field "idle_timeout"`
- **根因**: `idle_timeout` 不是 sing-box 入站的合法字段。sing-box 1.13.0 支持的正确字段是 `tcp_keep_alive`（初始间隔，默认5m）和 `tcp_keep_alive_interval`（探测间隔，默认75s）。`idle_timeout` 是凭直觉猜测的错误字段名
- **修复**: 
  1. 从服务器 config.json 移除 3 个 `idle_timeout` 字段
  2. 将 config_generator.py 中的 `idle_timeout` 替换为 `tcp_keep_alive: "30s"` + `tcp_keep_alive_interval: "15s"`
  3. 同步到服务器，重新生成配置，sing-box 恢复正常
- **教训**: 新增 sing-box 字段前必须先查官方文档（mcp_Context7_query-docs）确认字段合法性，不能凭直觉猜测字段名

### VLESS-Reality 速度退化修复 [TRAE SOLO CN]
- **现象**: JP-VLESS-Reality 节点长时间使用后速度变慢，切换节点再切回速度恢复
- **根因**: 
  1. `tcp_keepalive_time=600`（10分钟），NAT 超时后连接变"半死"
  2. 缺少 `tcp_no_metrics_save=1`，旧连接 RTT/拥塞窗口缓存影响新连接
  3. 客户端 VLESS-Reality 未显式禁用 multiplex（xtls-rprx-vision + mux 不兼容）
- **修复**: install.sh 修正 keepalive 参数，客户端配置添加 multiplex.enabled=false + tcp_fast_open=true

### 全协议暗病修复 [TRAE SOLO CN]
- **现象**: VLESS-WS/HTTPUpgrade/Trojan-WS/Hysteria2 速度慢且有丢包风险
- **根因**:
  1. Hysteria2 UDP 缓冲区默认值只有 208KB（rmem_default/wmem_default），QUIC 窗口耗尽
  2. CDN IP 池全是 104.16/104.17/104.19 段低质 IP
  3. CDN 协议缺少 multiplex 禁用和 tcp_fast_open
- **修复**: UDP 缓冲区增大到 2MB，CDN IP 替换为 8.39.125/162.159 段优质 IP，客户端配置统一添加 multiplex/tcp_fast_open

### 全协议深度优化 + cfnew 完整落地 [TRAE SOLO CN]
- **优化项**:
  1. VLESS-Reality 入站添加 tcp_keep_alive=30s + tcp_keep_alive_interval=15s（与 CDN 协议一致）
  2. Hysteria2 服务端入站添加 up_mbps=200 + down_mbps=200（匹配客户端 brutal 模式）
  3. Trojan-WS 客户端添加 utls 指纹伪装（chrome）+ multiplex 禁用 + tls.alpn
  4. 所有 CDN 协议客户端添加 tls.alpn=["http/1.1"]（显式匹配服务端）
  5. install.sh 新增 UDP/QUIC 专用参数：rmem_max/wmem_max=16MB, optmem_max=65536, udp_mem, TFO 黑洞禁用
  6. cdn_monitor 新增 TCP 下载速度测试（Cloudflare 10MB 测速文件），评分权重调整为延迟25%+速度20%+成功率25%+稳定性20%+新鲜度10%
  7. cdn_monitor 新增定期健康评估（每6小时），最优IP评分下降30%触发IP池刷新

## 最新排查（2026-05-22）

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
