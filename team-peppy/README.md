# Team Peppy · Huly v1

PT 工作区的独立 DSH 实例，部署在现有 Huly 主机 `/opt/team-peppy`。不替换原 `pop-super-agent`，不修改其状态目录或登录。

## 已接通的链路

Huly 的真实 Person mention → `dsh-superagent-huly` Source → DSH Trigger / Thread / Eval / Ticket / Assignment → 原 worker Session。回复经过原生 Outbox 返回原 Huly 线程。

Dashboard 直接查询 DSH Store，展示任务状态、最新报告和原 worker session。侧栏通过原生 SessionController 读取可见消息和文本流；补充指令经过 Engine.receive / attach，保留 Mandate 校验、原 session 和请求去重；中断仅取消当前轮。

明确 @ 的消息收到 ✅ 和线程状态，并要求实质性回复。每条机器人回复附原 worker session 的名称和 ID 链接，点击后直接打开对应侧栏。侧栏显示分析中、工具调用和当前轮状态，不展示内部思维链或原始工具参数。

首次 @ 后，同一线程的后续讨论进入上下文。未 @ 的消息只在 Router 或 worker 真正采纳处理后加标记；无关闲聊保持安静。原生 Eval 使用 auto，但 Source 只观察已经邀请机器人的线程，仍受成员名单、策略规则和 Mandate 限制。

没有新增任务数据库、轨迹存储、机器调度或身份钱包。这里的侧栏是服务器网页第一版，尚未替换 Pepper 的本地 Peppy 渲染器或添加桌面应用导航入口。

## 访问和权限

先在同一浏览器登录 PT，然后访问 `https://superagent-vps.tail0ac8b2.ts.net/team-peppy`。

Nginx 将其转到 `/files/<workspace UUID>/team-peppy/`，复用 Huly 的工作区范围 `presentation-metadata-Token` cookie。每次 API 请求通过 Huly 验证真实成员身份，并用该用户的令牌读取任务关联频道。其他来源混合的任务不在 v1 展示。接手权限限任务发起者、OWNER / ADMIN 或部署配置中的 operators。

只监听配置中的频道。新部署从启用时刻开始读取，不重放历史提及。成员在输入框选择真正的 **@Team Peppy** 联系人；纯文本拼写不视为授权提及。已订阅线程的后续消息无需重复 @。

## 在当前 Huly 主机部署

依赖主机现有 `huly-account-1`、`huly-transactor-1`、`huly-nginx-1`、网络 `huly_huly_net` 以及镜像 `pop-super-agent:8c32a9d`（DSH 0.2.1-rc.3 / Node 24 / pnpm 11.7）。这是一份针对当前主机的安装脚本，不是通用安装器。

1. 在 `dsh-superagent-prototype` 的 `codex/team-peppy-huly` 分支安装依赖，运行 `pnpm typecheck`、`pnpm test`，再运行 `pnpm build` 生成部署文件。
2. 将本目录脚本、compose 文件同步到 `/opt/team-peppy`；将 DSH 的 `lib/`、`team-peppy-ui/`、`package.json`、`cordis.patch.yml` 和本目录 Dockerfile、`.dockerignore` 放在 `/opt/team-peppy/release/`。每次同步前移除该 release 下旧的 `lib/` 和 `team-peppy-ui/`，避免散列文件名的旧编译产物残留；不要清理 `runtime/`、`config/` 或 `workspace/`。
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

## 验证、更新和回退

`python3 smoke.py` 在仅管理员、机器人和专用检查账号可见的私有频道执行真实测试，不向公共频道发消息。它检查创建任务、原 session 接手、相同请求只录入一次、原线程回帖、SSE 历史和越权拒绝。调用真实模型，通常需数分钟；保留检查任务和消息以便核对。

更新前备份 `/opt/team-peppy/runtime` 和 `config`，保留镜像 ID。只替换 release、构建新 tag，再以 `TEAM_PEPPY_VERSION=<tag> docker compose up -d app` 启动；同一状态目录不能同时启动两个实例。`deployed-revision.json` 记录部署的源提交和测试回执，不放密钥。

回退：选择上一镜像 tag 重建容器，保留原 runtime。停止本功能可运行 `docker compose stop app`；Nginx 变更前的备份为 `/opt/huly/.huly.nginx.before-team-peppy-*`。若恢复路由，先 `nginx -t` 再 reload。不要停整个 Huly compose 或删除 runtime。
