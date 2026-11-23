# Team Peppy · Huly v1

PT 工作区的独立 DSH 实例，部署在现有 Huly 主机 `/opt/team-peppy`。不替换原 `pop-super-agent`，不修改其状态目录或登录。

## 已接通的链路

Huly 的真实 Person mention → `dsh-superagent-huly` Source → DSH Trigger / Thread / Eval / Ticket / Assignment → 原 worker Session。回复经过原生 Outbox 返回原 Huly 线程。

Dashboard 直接查询 DSH Store，展示任务状态、最新报告和原 worker session。侧栏通过原生 SessionController 读取可见消息和文本流；补充指令经过 Engine.receive / attach，保留 Mandate 校验、原 session 和请求去重；中断仅取消当前轮。

明确 @ 的消息仍要求实质性回复。处理状态通过消息头右侧的浅灰图标和会话短名展示（最多六个字符，超出省略）；悬停查看完整名称和状态，点击在当前 Huly 右侧面板打开原 worker session。不再发送 ✅、状态回帖、自动接收确认或 worker 链接尾段。侧栏显示分析中、工具调用和当前轮状态，不展示内部思维链或原始工具参数。

首次 @ 后，同一线程的后续讨论进入上下文。未 @ 的消息只在 Router 或 worker 真正采纳处理后加标记；无关闲聊保持安静。原生 Eval 使用 auto，但 Source 只观察已经邀请机器人的线程，仍受成员名单、策略规则和 Mandate 限制。

没有新增任务数据库、轨迹存储、机器调度或身份钱包。这里的侧栏是服务器网页第一版，尚未替换 Pepper 的本地 Peppy 渲染器或添加桌面应用导航入口。

### 会话归属与上下文

输入真实 @Team Peppy 后，编辑器显示可选的「自动判断」入口。不选择时正常交给 Router；可以指定有接手权限的已有任务，或要求新建独立会话。手动选择的授权只在服务内存中短暂保留，消息仅携带不透明标识；到实际接收时再次使用成员身份检查当前频道和目标任务的所有关联频道。失效、重启或权限变化后明确显示失败，不回退自动执行。新建请求使用独立原生评估线程和 `newTicket` 标志，核心拒绝把它接到旧工单。指定已有会话通过原生 Engine.attach 绑定并保留原线程订阅，之后未 @ 的线程补充仍进入该 worker；明确指定的目标不会被悄悄改派。

同一 Huly 线程、同一任务只在最早的关联消息保留可点击的六字会话名；后续消息仅展示其自身的状态图标。完成后入口保留。无法解析的旧未完成接收记录以本次启用时间为界隐藏，不重放历史任务。仅讨论的回答打开讨论上下文，不创建或伪造 worker。

侧栏在「工作会话」和「上下文」间切换。上下文的关系图按真实频道和 Huly 线程分支汇总到任务；时间线按时间列出同一批消息、发送人、采纳状态和原消息链接。读取原生 Trigger、Ticket、Disposition，并以当前用户权限补充 Huly 线程回复；没有增加任务或轨迹存储。跨频道任务仍要求读者可以访问所有关联频道；混合来源任务继续关闭访问。

## 访问和权限

先在同一浏览器登录 PT，然后访问 `https://superagent-vps.tail0ac8b2.ts.net/team-peppy`。

Nginx 将其转到 `/files/<workspace UUID>/team-peppy/`，复用 Huly 的工作区范围 `presentation-metadata-Token` cookie。每次 API 请求通过 Huly 验证真实成员身份，并用该用户的令牌读取任务关联频道。其他来源混合的任务不在 v1 展示。接手权限限任务发起者、OWNER / ADMIN 或部署配置中的 operators。

只监听配置中的频道。新部署从启用时刻开始读取，不重放历史提及。成员在输入框选择真正的 **@Team Peppy** 联系人；纯文本拼写不视为授权提及。已订阅线程的后续消息无需重复 @。

## 在当前 Huly 主机部署

依赖主机现有 `huly-account-1`、`huly-transactor-1`、`huly-nginx-1`、网络 `huly_huly_net` 以及镜像 `pop-super-agent:8c32a9d`（DSH 0.2.1-rc.3 / Node 24 / pnpm 11.7）。这是一份针对当前主机的安装脚本，不是通用安装器。

1. 在 `dsh-superagent-prototype` 的 `codex/team-peppy-huly` 分支安装依赖，运行 `pnpm typecheck`、`pnpm test`，再运行 `pnpm build` 生成部署文件。
2. 将本目录脚本、compose 文件同步到 `/opt/team-peppy`；将 DSH 的 `lib/`、`team-peppy-ui/`、`prompts/`、`skills/`、`package.json`、`cordis.patch.yml` 和本目录 Dockerfile、`.dockerignore` 放在 `/opt/team-peppy/release/`。每次同步前移除该 release 下旧的 `lib/` 和 `team-peppy-ui/`，避免散列文件名的旧编译产物残留；不要清理 `runtime/`、`config/` 或 `workspace/`。
3. 在主机执行：

   ```sh
   cd /opt/team-peppy
   python3 provision.py --workspace pt
   docker compose build app
   docker compose up -d app
   python3 configure.py
   python3 expose.py
   ```

`provision.py` 使用 Huly 主机既有密钥引导创建普通 USER 机器人；只将该机器人的令牌挂载到运行容器，平台签名密钥不进入容器。独立 profile 从现有安装复制锁定依赖和模型配置，只选择性复制其引用的模型 API key，不复制浏览器登录或 DeepSeek 账号记录。首次部署需主机 Python PyYAML。

显式启用 `DSH_SUPERAGENT_HULY_ONLY=1`，GitHub Source 关闭，GitHub 身份和仓库为空；无法通过 gh 执行任务。执行目录在 `/workspace/tickets`，并发上限 2。机器人是当前容器里的执行用户，**不是额外安全沙箱**；挂载目录和容器网络就是当前执行边界。

`configure.py` 是首次部署的配置脚本，会覆盖原生 GitHub Source、Execution、Eval 和 Policy 区块。后续只升级镜像时不要重新执行它，以保留管理员修改的策略。

已有实例升级线程讨论行为时，只运行 `python3 conversation.py`。它保留现有成员名单、策略规则、模型和管理员提示配置，启用受限线程观察，并加入 @ 必答、未 @ 按相关性介入的对话规则；该脚本可重复运行。

## Instances 连通性检查

Instances 的「Team Peppy」检查从运行 DSH 的 `app` 容器直接连接已登记的 Tailscale IP 和 TCP 端口。此结果反映 Team Peppy 的运行网络。迁移部署时，在新的运行环境配置目标网络路由和访问权限。

管理员在 Chat 右侧「+」中打开 Instances，登记机器和服务，然后在「配置授权」中选择端口、Huly 成员和对应的 Tailscale 登录名。选择多个端口可按账号白名单提交整批规则，等待应用期间可以从任一关联端口的「查看规则」重新打开。单端口授权也支持选填 Tailscale 组。Tailscale 管理员将生成的片段合并到现有 Tailnet 策略，通过策略测试后，Huly 管理员记录已应用。撤权时先隐藏 Pepper 入口，再移除 Tailnet 规则，运行生成的拒绝测试并记录结果。成员在 Mac 上用授权登记的 Tailscale 登录名打开获授权服务。HTTPS 使用目标设备的 MagicDNS 名称和证书，SSH 使用本机 SSH 客户端与设备已有的登录规则。

工作区所有者或管理员可在 Huly「工作区设置 → 成员」授予或撤销成员的 Instances 管理权限。服务通过 Compose 中的 `HULY_ACCOUNTS_URL` 核对实时工作区成员身份。

## 验证、更新和回退

`python3 smoke.py` 在仅管理员、机器人和专用检查账号可见的私有频道执行真实测试，不向公共频道发消息。它检查创建任务、原 session 接手、相同请求只录入一次、原线程回帖、SSE 历史和越权拒绝。调用真实模型，通常需数分钟；保留检查任务和消息以便核对。

更新前备份 `/opt/team-peppy/runtime` 和 `config`，保留镜像 ID。只替换 release、构建新 tag，再以 `TEAM_PEPPY_VERSION=<tag> docker compose up -d app` 启动；同一状态目录不能同时启动两个实例。`deployed-revision.json` 记录部署的源提交和测试回执，不放密钥。

回退：选择上一镜像 tag 重建容器，保留原 runtime。停止本功能可运行 `docker compose stop app`；Nginx 变更前的备份为 `/opt/huly/.huly.nginx.before-team-peppy-*`。若恢复路由，先 `nginx -t` 再 reload。不要停整个 Huly compose 或删除 runtime。

### 消息头版本上线

前端在 `huly-superagent-desktop` 的 Mac 发布流程中构建，Mac 包和 Huly 网页使用同一份已验证的 `dev/prod/dist`。将其同步到 Huly 主机的一个新目录（目录下保留 `dist/`），然后执行：

```sh
python3 /opt/team-peppy/deploy-headers.py --frontend /opt/team-peppy/frontend-release/SOURCE --source FULL_SOURCE_SHA --dsh-version header-c76c755
python3 /opt/team-peppy/conversation.py
python3 /opt/team-peppy/smoke.py --conversation
```

`deploy-headers.py` 只替换 frontend 镜像和 Team Peppy 镜像；用 YAML 源位置仅更新 `front.image`，保留现有 Compose `!reset` 和其他配置。后台镜像变化时，它停止独立 Team Peppy 服务后备份 runtime 和配置，保留原 master/session 命名空间，分别检查新服务就绪，失败时回退镜像；后台镜像已相同时跳过重启。备份位于 root 私有的 `/opt/team-peppy/backups/message-headers-*`。不更新 Huly model、数据库、账号或其他服务。

2026-11-23 上线验证：Huly 前端 `ad863ff`、DSH `c76c755`，原 master/session 命名空间保持一致。65 个测试文件、1,226 项测试通过；真实私有频道验证了消息头绑定、原会话接手和 SSE、无新 emoji 回执/会话尾注、未 @ 上下文静默、相关讨论采纳和讨论不额外创建 worker。Huly 网页入口已核对为新产物。Mac `0.1.10-peppy.21` 已由 [发布流程](https://github.com/l1mzh0317/huly-superagent-desktop/actions/runs/45102884137) 发布，更新服务验签通过，差分基线为 `.20`、`.19`、`.18`。本次未构建 Windows，也未同步安装包镜像。


2026-11-23 会话上下文版本：Huly 前端 `aaa97367fad0c5eef82c0aac424e226fed375dbf`，DSH `b5c76e4ca086489b1802a1c7bedd43650ee560a1`，66 个测试文件、1,241 项测试通过。编译后的真实 Svelte 组件与 Dashboard 浏览器检查覆盖可选会话选择、跨工作区清空、菜单不被编辑器裁切、关系图／时间线切换、原 worker 接手、键盘操作及 320px 布局。专用私有频道验证了跨频道指定同一个 worker、指定线程之后未 @ 的补充进入原 worker、静默上下文、入口合并、新会话独立执行，以及完成后保留可点击名称。部署后再次检查了原 master 不变、跨频道上下文和完成入口保留，公网 Huly index 与 Actions 验证产物一致。

Mac `0.1.10-peppy.22` 已由 [Actions](https://github.com/l1mzh0317/huly-superagent-desktop/actions/runs/45129023459) 构建并[发布](https://github.com/l1mzh0317/huly-superagent-desktop/releases/tag/0.1.10-peppy.22)，Windows 构建已跳过。Huly 主机更新服务验签通过，差分基线为 `.21`、`.20`、`.19`；未向 HTTPS 服务同步完整安装包镜像。部署备份为 `/opt/team-peppy/backups/message-headers-1795418721`，真实验证记录为 `/opt/team-peppy/test-receipts-session-routing-final.jsonl`。
