---
name: wechat-group-daily-report
description: >-
  生成微信群聊可视化日报（Markdown 聊天记录 + Agent 结构化分析 + HTML/PNG）。
  WeChatDaily 项目专用 Skill。当用户提到微信群日报、群聊报告、群分析、
  导出群聊天记录、生成 HTML 群报时使用。
---

# 微信群聊日报生成

## 概述

在 **WeChatDaily** 项目中，将指定群、指定日期的聊天记录导出为 Markdown，由 **当前 Agent** 做结构化话题分析，再渲染为 HTML（可选 PNG）。

**项目根目录**：含 `wechat.py`、`.env`、`export/` 的目录。

## 前置检查

开始流程前 silently 确认：

- [ ] `tools/wechat-decrypt/key_scan_common.py` 存在（子模块已初始化）
- [ ] `pip install -r requirements.txt` 已执行（Python 3.14+）
- [ ] `.env` 已配置 `WX_RAW_KEY`（见 [references/env-setup.md](references/env-setup.md)）
- [ ] 已执行过至少一次 `setup` + `decrypt`（或用户确认本次要刷新）

若缺子模块：`git submodule update --init --recursive`，或手动克隆 WeChatDecrypt 到 `tools/wechat-decrypt/`。

---

## 工作流（必须按序执行）

复制进度清单：

```
- [ ] Step 1 确认群名
- [ ] Step 2 确认日期
- [ ] Step 3 确认是否刷新解密
- [ ] Step 4 导出聊天记录 MD
- [ ] Step 5 Agent 分析 → JSON
- [ ] Step 6 渲染 HTML (+ PNG)
- [ ] Step 7 交付路径
```

### Step 1：确认群名

使用 `AskQuestion`（或对话）询问用户要分析哪个/哪些群。

**辅助**：先运行列出可选群（需已 decrypt）：

```powershell
python wechat.py groups
```

- 支持多个群：逗号分隔，与 `groups` 命令显示名一致
- 群名含逗号时用引号包裹整个 `--groups` 参数

**示例提问**：

> 要生成哪几个群的日报？可回复群名片段。

### Step 2：确认日期

使用 `AskQuestion` 询问日期。

- **默认**：当天，`YYYY-MM-DD`（本地时区）
- 用户未指定则用今天

**示例提问**：

> 分析哪一天的数据？默认今天 `{today}`。

### Step 3：确认是否拉取最新数据

使用 `AskQuestion`：

> 是否需要重新解密最新微信数据？（微信重启后 key 会变，建议选「是」）

**选「是」** → 执行（在项目根目录）：

1. 从 `.env` 读取 `WX_RAW_KEY`（缺失则提示用户按 [env-setup.md](references/env-setup.md) 配置）
2. Setup：

```powershell
python wechat.py setup --raw-key $env:WX_RAW_KEY
```

若 `.env` 有 `WECHAT_DB_DIR`：

```powershell
python wechat.py setup --raw-key $env:WX_RAW_KEY --db-dir $env:WECHAT_DB_DIR
```

3. Decrypt：

```powershell
python wechat.py decrypt
```

**选「否」** → 跳过，直接使用 `export/decrypted/` 现有库。

### Step 4：导出聊天记录（MD）

对每个目标群，**一次命令**导出：

```powershell
python wechat.py export --date {date} --groups {群1,群2} --limit 99999
```

说明：

- `--limit 99999`：尽量导出当日全部消息（默认仅 1000）
- 输出：`export/reports/report_{date}.md`（多群时同一文件内 `## 群名` 分节）

确认 MD 中 `_消息数: N 条_` 与预期一致。

### Step 5：Agent 结构化分析（核心）

**禁止**在项目中配置 API Key 或调用任何内置 LLM 接口。

对每个群分别：

1. 读取 [references/analysis-prompt.md](references/analysis-prompt.md) 中的 Prompt 模板
2. 从 `export/reports/report_{date}.md` 提取该群 `### 聊天记录` 代码块全文
3. 以 Agent 身份分析，**只输出 JSON**（格式见 analysis-prompt.md）
4. 写入：

```
export/reports/analysis_{date}_{safe_group}.json
```

`safe_group` = 群名中非法文件名字符替换为 `_`，最长 60 字符（与 `render_manual_report.py` 一致）。

消息极多时分批阅读 MD，但 JSON 必须覆盖全天主要话题，勿只分析开头。

### Step 6：渲染 HTML 与 PNG

每个群执行：

```powershell
python scripts/render_manual_report.py --group "{群名}" --date {date} --analysis-json export/reports/analysis_{date}_{safe_group}.json --png
```

产出：

- `export/reports/report_{date}_{safe_group}.html`
- `export/reports/report_{date}_{safe_group}.png`（需 `python -m playwright install chromium`）

若 PNG 失败：仍交付 HTML，并提示安装 Chromium。

### Step 7：交付

向用户汇总：

| 类型 | 路径 |
|------|------|
| 完整聊天记录 | `export/reports/report_{date}.md` |
| 结构化分析 | `export/reports/analysis_{date}_{群}.json` |
| 可视化日报 | `export/reports/report_{date}_{群}.html` |
| 图片版 | `export/reports/report_{date}_{群}.png` |

---

## 关键约束

| 项 | 规则 |
|----|------|
| 分析者 | 当前 Agent，项目不内置 LLM |
| 导出 | `export` 或 `report` 命令只写 MD |
| 密钥 | 只从 `.env` 的 `WX_RAW_KEY` 读取，勿写入 Skill 或提交 Git |
| HTML 模板 | `src/visual_report.py` 的 `render_html_report` |
| 多群 | Step 5–6 **按群循环** |

---

## 故障排查

| 现象 | 处理 |
|------|------|
| `No module named 'key_scan_common'` | 初始化 `tools/wechat-decrypt` |
| `raw_key 验证失败` | 微信登录后重跑 wx_key，更新 `.env` |
| MD 只有少量消息 | 加大 `--limit`，或检查 decrypt 是否最新 |
| `未找到群` | `python wechat.py groups` 核对精确群名 |
| PNG 失败 | `pip install playwright` + `python -m playwright install chromium` |

---

## 参考文件

- [analysis-prompt.md](references/analysis-prompt.md) — 结构化分析 Prompt（ verbatim ）
- [env-setup.md](references/env-setup.md) — `.env` 与 `WX_RAW_KEY` 配置
