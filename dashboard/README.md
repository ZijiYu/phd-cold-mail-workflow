# 套磁工作台 / Outreach dashboard

本地运行的可视化面板和 REST API。它直接读写 skill 生成的申请季文件夹，所以面板和 agent 看到的始终是同一份数据：

```text
outreach/
|-- spring-2027/          # 一个申请季一个文件夹，面板左上角切换
|   |-- programs.csv      # 选校
|   |-- targets.csv       # 选导师 + 套磁状态
|   `-- drafts/*.md       # 邮件草稿（首封、跟进、回复）
`-- fall-2027/
```

- **申请季**：每个子文件夹是一个申请季，例如 `spring-2027`、`fall-2027`，面板左上角切换。点切换框旁边的 “+” 可以新建一个空的申请季。

- **侧栏**：按截止日期排列的学校，每所学校下列出教授和状态。可以搜索，也可以筛选“待处理 / 进行中 / 已结束”。学校标题是一条带色边的高亮条，滚动时会固定在顶部。
- **学校排名**：每所学校旁边显示 CSRankings 美国排名，例如 `#24 AI #32`：前一个是综合排名，后一个是 AI 方向（AI、视觉、ML、NLP、信息检索）。颜色按综合排名分档：金色是前 20，蓝色是 21–50，灰色是 50 名以后。数据在 `app/rankings.json`，更新方法：`git clone --depth 1 https://github.com/emeryberger/CSrankings /tmp/csr && python dashboard/tools/build_rankings.py /tmp/csr`。学校名对不上时（显示“未排名”），在 `app/rankings.py` 的 `ALIASES` 里加一行简称。
- **总览**：套磁进度路线（调研 → 起草 → 定稿 → 已发送 → 有回音）、需要处理的事项、各学校的联系与回复情况。
- **教授页**：编辑草稿（⌘/Ctrl+S 保存，自动运行 `check_draft.py`）、查看 Gmail 往来、编辑资料与 fit 分项、更改状态。
- **Gmail**：识别你已发出的邮件、教授回信、自动回复和退信，以**建议**的形式展示，由你确认后才更新；把定稿推送到 Gmail 草稿箱。**面板不会发送邮件**，发送仍在 Gmail 里手动点。
- **REST API**：上面所有操作都有接口，文档在 `/api/docs`。

## 运行

### 快速启动：`phd` 命令

第一次在仓库根目录运行一次：

```bash
dashboard/phd install    # 把 phd 命令加进 ~/.zshrc（重复运行只会更新，不会重复添加）
```

新开一个终端窗口后，在任何目录都可以用：

| 命令 | 作用 |
|---|---|
| `phd` | 后台启动面板并打开浏览器；已经在运行就只打开浏览器 |
| `phd stop` | 停止 |
| `phd restart` | 重启 |
| `phd status` | 是否在运行 |
| `phd logs` | 查看日志（Ctrl+C 退出查看，面板继续运行） |
| `phd update` | `git pull` 拉取最新代码，并在运行中时自动重启 |
| `phd run` | 在前台运行（Ctrl+C 停止） |

- 后台运行，关掉终端窗口面板也不会停。
- 第一次启动会在 `dashboard/.venv` 建虚拟环境并安装依赖，大约十几秒；之后启动约 1 秒。依赖只在 `requirements.txt` 变化时才重新安装。
- 需要 Python 3.10 以上。脚本会自动找 `python3.13`…`python3.10`；macOS 自带的 `python3` 通常是 3.9，不够的话 `brew install python@3.12`，或用 `PYTHON=/path/to/python3 phd` 指定。
- 可选环境变量：`PHD_DATA`（数据文件夹，默认仓库里的 `outreach/`）、`PHD_PORT`（默认 8765）、`PHD_NO_BROWSER=1`（不自动打开浏览器）。
- 日志在 `~/.phd-outreach-dashboard/dashboard.log`。

### 前台运行

```bash
dashboard/start.sh                    # 读取 ./outreach（不存在会自动创建）
dashboard/start.sh path/to/outreach   # 指定自己的申请季文件夹
```

`start.sh` 等同于 `phd run`。也可以手动运行：

```bash
pip install -r dashboard/requirements.txt
python -m dashboard --data outreach --open
```

默认地址是 http://127.0.0.1:8765/ ，只监听本机。在终端按 Ctrl+C 停止。

### 用 Docker 运行

不想在本机装 Python 依赖，可以用 Docker（需要先装好并打开 Docker Desktop）。在仓库根目录运行：

```bash
docker compose -f dashboard/compose.yaml up -d --build   # 构建并在后台启动
docker compose -f dashboard/compose.yaml logs -f         # 查看日志
docker compose -f dashboard/compose.yaml down            # 停止
```

- 地址同样是 http://127.0.0.1:8765/ 。端口只绑定在 `127.0.0.1`，别的设备访问不到。
- 数据目录 `./outreach` 挂载到容器里，和 `start.sh`、skill 用的是同一份文件。
- 令牌和 Gmail 授权存在 `~/.phd-outreach-dashboard`，也挂载进容器，所以和本地运行时共用，不用重新连接 Gmail。
- 容器设置了 `restart: unless-stopped`，Docker Desktop 打开时会自动启动面板。
- Docker 和 `start.sh` 都用 8765 端口，同一时间只能运行其中一个。
- 改了代码后重新执行第一条命令（带 `--build`）即可更新。

面板和 skill 是两个独立的文件夹。面板不需要放进 skills 目录，它用的检查脚本是 `cold-email/scripts/` 的副本，放在 `app/checks/`；两份不一致时 `test_checks_in_sync.py` 会报错。

本地状态存放在 `~/.phd-outreach-dashboard/`（可以用 `--state-dir` 修改），不在仓库里：

| 文件 | 内容 |
|---|---|
| `api_token` | REST API 的访问令牌 |
| `google_client.json` | 你自己的 Google OAuth 客户端（需要手动放进来） |
| `google_token.json` | Gmail 授权令牌（连接后自动生成，权限 600） |
| `gmail_state.json` | 同步结果和 Gmail 草稿 ID |

## 绑定 Gmail

面板通过**你自己的** Google Cloud OAuth 客户端连接 Gmail（Google 不允许跳过这一步），凭据只保存在你的电脑上。全部在面板里完成：

1. 点右上角 **“连接 Gmail”**，打开设置向导。向导里每一步都有“打开”按钮，直接跳到 Google Cloud 对应的页面：
   1. 启用 Gmail API（没有项目会先让你建一个）；
   2. 设置授权页面：用户类型选 External，不用提交审核；
   3. 在 Audience → Test users 里加上你自己的 Gmail；
   4. 创建客户端，类型选 **桌面应用（Desktop app）**，下载 JSON。
2. 把下载的 JSON **拖进向导**（也可以手动填写客户端 ID 和密钥），点 **“保存并前往 Google 授权”**，页面会直接跳到 Google 授权页。
3. 在 Google 页面选择账号，勾选两项权限，授权后自动回到面板。

之后再连接，或者授权过期需要续期，都是点一下按钮直接跳到 Google 授权页，并且预选好你的账号。

申请的权限只有两项：

- `gmail.readonly`：查找发给教授的邮件、教授的回信和退信，读取邮件线程。没勾选这一项时，面板不会保存授权，并会提示你重新连接。
- `gmail.compose`：创建和更新草稿。没勾选时，面板可以同步回信，但不能推送草稿，右上角会提示“缺草稿权限”。

Google 没有“只能管理草稿”的权限，`gmail.compose` 在技术上也允许发送。这个面板的代码从不调用发送接口，测试里也专门检查了这一点。

**7 天过期**：Testing 状态下，Google 的授权大约 7 天后失效。面板会自动识别，右上角显示“Gmail 授权已过期 · 重新连接”，点一下就能续期。

**常见问题**

- Google 显示“应用被阻止”或“access_denied”：你的 Gmail 不在测试用户名单里（第 3 步）。
- `redirect_uri_mismatch`：客户端类型选成了“Web 应用”。向导会拒绝这种文件，请重建为“桌面应用”。
- 想换一个 Google 客户端：点邮箱旁边的“…”，选“更换 Google 客户端”。

### 同步规则

点“同步 Gmail”后，面板会逐个检查有邮箱的教授，并给出建议：

| 发现 | 建议 |
|---|---|
| 状态还是“定稿”，但已发件里有发给他的邮件 | 改为“已发送”，填好发送日期和跟进日 |
| 发送后收到回信 | 改为“已回复”，填好回信摘要 |
| 收到自动回复 | 状态不变，把跟进日顺延 |
| 收到退信 | 改为“退信”，提示重新核实邮箱 |
| 你在 Gmail 里已经发了跟进 | 更新跟进次数，清空跟进日 |

每条建议都要你点“应用”才会写入 `targets.csv`，也可以点“忽略”。

### 推送草稿的条件

- **首封**：状态必须是“已定稿”。只有当首封草稿通过检查（没有占位符或 TODO）时，才能把状态改成“已定稿”。
- **跟进或回复**：首封发出之后才能推送。如果已经同步过，草稿会挂在原来的邮件线程下（带 `In-Reply-To`）。
- 再次推送会更新 Gmail 里的同一封草稿，不会重复创建。

## REST API

所有 `/api` 接口都需要令牌：

```bash
TOKEN=$(cat ~/.phd-outreach-dashboard/api_token)
API=http://127.0.0.1:8765/api

curl -H "Authorization: Bearer $TOKEN" $API/campaigns
curl -H "Authorization: Bearer $TOKEN" "$API/campaigns/fall-2027/targets?status=sent"
curl -H "Authorization: Bearer $TOKEN" $API/campaigns/fall-2027/summary

curl -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"status": "closed", "close_reason": "not recruiting"}' \
     $API/campaigns/fall-2027/targets/riverside--ben-osei
```

主要接口如下，完整的参数和示例见 http://127.0.0.1:8765/api/docs ：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/campaigns` | 列出申请季 |
| GET | `/campaigns/{c}/summary` | 状态统计、到期跟进、数据问题、各学校汇总 |
| GET | `/campaigns/{c}/programs` | 项目列表 |
| GET / POST | `/campaigns/{c}/targets` | 列出（可筛选）/ 添加教授 |
| GET / PATCH | `/campaigns/{c}/targets/{id}` | 读取 / 更新教授（状态变更会校验） |
| GET / POST | `/campaigns/{c}/targets/{id}/drafts` | 列出 / 新建草稿（`first`、`followup`、`reply`） |
| GET / PUT | `/campaigns/{c}/targets/{id}/drafts/{name}` | 读取 / 保存草稿 |
| POST | `/campaigns/{c}/targets/{id}/drafts/{name}/check` | 运行草稿检查 |
| POST | `/campaigns/{c}/targets/{id}/drafts/{name}/gmail` | 推送到 Gmail 草稿箱 |
| POST | `/campaigns/{c}/gmail/sync` | 同步 Gmail，返回建议 |
| GET | `/campaigns/{c}/targets/{id}/thread` | 与该教授的最近一个邮件线程 |
| DELETE | `/campaigns/{c}/targets/{id}/suggestion` | 忽略 Gmail 建议 |
| GET / POST | `/gmail/status`、`/gmail/connect`、`/gmail/disconnect` | Gmail 连接状态与授权 |

### 安全

- 默认只监听 `127.0.0.1`。如果用 `--host` 改成其他地址，面板会打印警告。
- 所有 `/api` 请求都需要令牌。页面本身会内嵌令牌，但其他网站读不到它。
- `Host` 不是本机地址的请求一律拒绝，防止 DNS rebinding。
- Gmail OAuth 使用 PKCE 和一次性的 `state`，令牌文件权限为 600。
- 草稿路径限制在申请季文件夹内，`targets.csv` 采用原子写入，并保留你自己加的列。

## 测试

```bash
python -m unittest discover dashboard/tests
```

测试用一个假的 Google 后端（`dashboard/tests/fake_google.py`）覆盖整个流程：OAuth、同步建议、邮件线程、草稿推送和断开连接，并检查面板从未调用过发送接口。
