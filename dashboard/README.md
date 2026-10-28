# 套磁工作台 / Outreach dashboard

本地运行的可视化面板和 REST API。它直接读写 skill 生成的申请季文件夹，所以面板和 agent 看到的始终是同一份数据：

```text
outreach/
`-- fall-2027/
    |-- programs.csv      # 选校
    |-- targets.csv       # 选导师 + 套磁状态
    `-- drafts/*.md       # 邮件草稿（首封、跟进、回复）
```

- **侧栏**：按截止日期排列的学校，每所学校下列出教授和状态。可以搜索，也可以筛选“待处理 / 进行中 / 已结束”。
- **总览**：套磁进度路线（调研 → 起草 → 定稿 → 已发送 → 有回音）、需要处理的事项、各学校的联系与回复情况。
- **教授页**：编辑草稿（⌘/Ctrl+S 保存，自动运行 `check_draft.py`）、查看 Gmail 往来、编辑资料与 fit 分项、更改状态。
- **Gmail**：识别你已发出的邮件、教授回信、自动回复和退信，以**建议**的形式展示，由你确认后才更新；把定稿推送到 Gmail 草稿箱。**面板不会发送邮件**，发送仍在 Gmail 里手动点。
- **REST API**：上面所有操作都有接口，文档在 `/api/docs`。

## 运行

在仓库根目录运行：

```bash
dashboard/start.sh                    # 有 ./outreach 就用它，否则用虚构的示例数据
dashboard/start.sh path/to/outreach   # 指定自己的申请季文件夹
```

第一次运行会在 `dashboard/.venv` 里建虚拟环境并安装依赖（需要 Python 3.10+）。也可以手动运行：

```bash
pip install -r dashboard/requirements.txt
python -m dashboard --data dashboard/sample/outreach --open
```

默认地址是 http://127.0.0.1:8765/ ，只监听本机。在终端按 Ctrl+C 停止。

面板和 skill 是两个独立的文件夹。面板不需要放进 skills 目录，它用的检查脚本是 `cold-email/scripts/` 的副本，放在 `app/checks/`；两份不一致时 `test_checks_in_sync.py` 会报错。

本地状态存放在 `~/.phd-outreach-dashboard/`（可以用 `--state-dir` 修改），不在仓库里：

| 文件 | 内容 |
|---|---|
| `api_token` | REST API 的访问令牌 |
| `google_client.json` | 你自己的 Google OAuth 客户端（需要手动放进来） |
| `google_token.json` | Gmail 授权令牌（连接后自动生成，权限 600） |
| `gmail_state.json` | 同步结果和 Gmail 草稿 ID |

## 绑定 Gmail

面板通过**你自己的** Google Cloud 项目连接 Gmail，凭据只保存在你的电脑上。

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)，新建一个项目。
2. 在“API 和服务 → 库”里启用 **Gmail API**。
3. 配置 **OAuth 同意屏幕**：用户类型选 External，发布状态保持 Testing，并把你自己的 Gmail 地址加为测试用户。
4. 在“凭据”里创建 **OAuth 客户端 ID**，应用类型选 **桌面应用（Desktop app）**，然后下载 JSON。
5. 把下载的文件保存为 `~/.phd-outreach-dashboard/google_client.json`。
6. 刷新面板，点右上角的“连接 Gmail”，在 Google 页面完成授权。

申请的权限只有两项：

- `gmail.readonly`：查找发给教授的邮件、教授的回信和退信，读取邮件线程。
- `gmail.compose`：创建和更新草稿。

Google 没有“只能管理草稿”的权限，`gmail.compose` 在技术上也允许发送。这个面板的代码从不调用发送接口，测试里也专门检查了这一点。Testing 状态下的授权大约 7 天后会失效，到时重新点一次“连接 Gmail”即可。

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
