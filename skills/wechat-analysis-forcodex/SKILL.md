---
name: wechat-analysis-forcodex
description: 微信聊天记录总结与趣味图片生成的 Codex 专属独立技能。用于用户要求按指定微信群聊或私聊、指定时间范围、指定输出风格，总结本机微信聊天记录，并使用 Codex 内置生图能力生成海报、朋友圈图、趣味总结图片时；也用于总结某个人的群聊故事线、某个话题/八卦/事件链路，并基于聊天画像生成真人随拍风虚构形象；还用于在只有本技能目录的电脑上完成 raw_key 校验、微信数据库解密、会话列表、聊天范围导出、故事线素材抽取、重复 message 数据库合并去重，以及自己名称不能显示为“我”的导出任务。
---

# 微信聊天总结生图

## 核心目标

在任意电脑的 Codex 中，按用户指定的聊天对象、时间范围、人物、话题和风格读取本机微信聊天记录，生成总结或故事线；如果用户要求图片，使用 Codex 内置 `image_gen` 直接生成 raster 图片，不走 HTML 渲染或截图。

本 skill 可复制到：

```text
%USERPROFILE%\.codex\skills\wechat-analysis-forcodex
```

脚本入口：

```powershell
python .\scripts\wechat_analysis.py --help
```

如果 `python` 不可用，让用户指定可用 Python 路径。只需要安装 `pycryptodome`。

## 工作目录

默认工作目录：

```text
%USERPROFILE%\.codex\wechat-analysis-forcodex
```

所有配置、`all_keys.json`、解密库、导出 Markdown/JSON、生成图片都写到工作目录。不要把敏感文件写进 skill 目录。

可用 `--work-dir` 覆盖默认位置。

## 首次设置

1. 用户需要先通过 wx_key 或其他方式取得 64 位 hex `raw_key`。本 skill 不内置也不分发 `wx_key.exe`。
2. 运行检查：

```powershell
python .\scripts\wechat_analysis.py doctor
```

3. 初始化配置并生成 `all_keys.json`：

```powershell
python .\scripts\wechat_analysis.py setup --raw-key "<64位raw_key>" --self-name "<自己的群昵称>"
```

如果自动检测到多个 `db_storage`，根据候选重新传：

```powershell
python .\scripts\wechat_analysis.py setup --raw-key "<64位raw_key>" --db-dir "<db_storage路径>" --self-name "<自己的群昵称>"
```

4. 解密：

```powershell
python .\scripts\wechat_analysis.py decrypt
```

## 会话和导出

列出会话：

```powershell
python .\scripts\wechat_analysis.py sessions --filter "示例群聊"
```

导出指定范围：

```powershell
python .\scripts\wechat_analysis.py export --chat "示例群聊" --start 2026-06-18 --end 2026-06-24 --self-name "<自己的群昵称>"
```

抽取人物或话题故事线素材：

```powershell
python .\scripts\wechat_analysis.py story --chat "示例群聊" --person "示例成员" --alias "示例别名" --self-name "<自己的群昵称>"
python .\scripts\wechat_analysis.py story --chat "示例群聊" --topic "示例话题" --alias "示例关键词" --self-name "<自己的群昵称>"
```

规则：

- `--end` 包含当天全天。
- 聊天对象按 username、备注、昵称、session 信息匹配。
- 多个候选时不要猜，让用户指定更精确的名称或 username。
- 同一 `Msg_<md5>` 表出现在多个 `message_*.db` 时，脚本会合并并去重。
- 输出在工作目录 `reports` 下。
- 群聊导出的成员展示名必须优先使用群昵称/群名片；只有读不到群昵称时才回退到好友备注、微信昵称或 username。
- `story --person` 和 `story --topic` 二选一；`--alias` 可重复传入群昵称、备注、外号或相关关键词。
- `story --start/--end` 可选，不传时使用该会话当前解密库内全量范围。

## 自己名称规则

禁止把自己发出的消息显示为 `我`。

群聊中 `--self-name` 优先填写自己的群昵称，不要填好友备注或账号昵称。

自己名称优先级：

1. `export --self-name` 显式传入值。
2. `setup --self-name` 写入的配置值。
3. 从消息内容、群名片或联系人信息中可明确解析出的本人名称。

如果记录里存在 `real_sender_id=2` 的自己消息，但无法解析或配置自己的名称，`export` 必须失败并提示补 `--self-name`。不要静默使用 `我`、`self`、`?`。

## 总结规则

阅读导出的 Markdown 后再总结。不要把原始聊天全文贴回给用户。

总结应包含：

- 实际日期范围和消息条数。
- 主要话题，按连续对话和语义聚合。
- 活跃日期、活跃成员、整体氛围。
- 用户指定风格下的表达，例如趣味、正式、简短、朋友圈文案。

人物/话题故事线：

- 先运行 `story` 抽取素材，再阅读输出的 `story_*.md/json`。
- 人物故事线按 sender、群昵称、备注、昵称、用户补充别名匹配；群昵称存在时，输出姓名使用群昵称。
- 话题故事线按关键词、别名和相关成员上下文窗口聚合。
- 必须亲自阅读窗口材料后做语义总结，不只罗列关键词。
- 按时间线、分支事件、关键人物关系、群友反应和结论组织。
- 需要详细规则时读取 `references\storyline-workflow.md`。

隐私要求：

- 不输出手机号、密钥、二维码、链接 token 等敏感信息。
- 不输出大段原始聊天记录。
- 不给成员起攻击性外号。
- 对 `?` 或未知成员，说明是导出工具未解析出昵称，不强行猜人。

## 内置生图

当用户要求生成图片、海报、朋友圈图、趣味总结图片时：

1. 使用内置 `image_gen` 工具。
2. 不使用 HTML 渲染，不生成 HTML 后截图。
3. 图片内容基于总结后的主题，不展示原始聊天截图。
4. 生图前必须先读取 `references\style-index.md`。如果用户点名了风格、IP、游戏、媒介或关键词，按 `style-index.md` 的“硬路由表”选择风格；不要凭模型自己的理解跳过模板。
5. 选定风格后必须读取对应的单个风格文件，并按该文件的 Required visible text、Section 标题、Composition、Palette、Constraints 组织 `image_gen` 提示词；不要自行替换成另一套版式或栏目名。
6. 默认日报风格选择 `avatar-daily`，再读取 `references\avatar-daily-prompt-template.md`。
7. 用户要“新鲜”“创意”“换个风格”但没有点名方向时，从 `style-index.md` 选择一个创意风格，再只读取对应文件，例如 `style-starship-log.md`、`style-card-compendium.md`、`style-radio-program.md`、`style-convenience-shelf.md` 或 `style-valorant-tactical.md`。
8. 用户要求人物/话题故事线长图时，读取 `references\story-handbook-prompt-template.md`。
9. 用户要求根据聊天画像生成真人、真实照片、手机随拍风形象时，读取 `references\persona-photo-style-index.md`，再读取 `references\persona-photo-realism-rules.md` 和选中的单个真人画像预设。
10. 真人画像必须表述为“基于聊天气质的虚构真人感用户画像”，不声称真实还原本人长相，不使用真实头像、微信 ID、手机号等身份信息。
11. 真人画像追求“自然好看 + 真人可信”，不要塑料磨皮、模板网红脸、CG 感、棚拍写真或 AI 海报质感；也不要故意增加明显瑕疵。
12. 真人画像默认年龄：用户未明确指定年龄时，一律按 18-25 岁年轻成人绘制；如果成片看起来明显超过 25 岁，视为年龄不符，必须重画。
13. 为群友角色卡或真人画像生成形象时，优先使用导出 JSON 的 `speaker_profiles[*].gender` 或 `story_*.json` 的 `gender`：
   - `male`：男性化但不过度刻板的小像。
   - `female`：女性化但不过度刻板的小像。
   - `unknown`：中性小像。
   - 不要按名字猜性别；微信读不到性别就用中性形象。
14. 每个角色用称号和道具表达聊天气质，例如扳手、讲台、蓝图、文件夹、扩音器、雷达。
15. 真人画像生成后必须用 `view_image` 检查；如果脸太假、年龄不符、默认年龄下看起来超过 25 岁、场景不明显、AI 感重或明显肢体/道具错误，重新生成一版再交付。
16. 生图后复制图片到工作目录：

```text
reports\<safe_chat>_<start>_to_<end>_<style>.png
```

## 验证和交付

最小验证：

- `doctor` 显示 Python 和 `pycryptodome` 可用。
- `setup` 成功生成 `all_keys.json`。
- `decrypt` 成功解密至少 `contact`、`session`、`message` 相关数据库。
- `export` 输出 Markdown 和 JSON，且自己消息不显示为 `我`。
- JSON 包含 `speaker_profiles`；能从微信读到性别时，成员画像使用 `male` 或 `female`，读不到时为 `unknown`。
- `story` 输出 Markdown 和 JSON，包含 `target_type`、`target`、`aliases`、`profile`、`gender`、`target_message_count`、`top_days`、`topic_counts`、`relevant_windows`、`first_time`、`last_time`。

最终回复给用户：

- 实际聊天对象和日期范围。
- 消息条数。
- 总结结果。
- Markdown/JSON 路径。
- 图片路径，若生成了图片。
- 真人画像必须说明“这是虚构真人感画像，不是真人还原”。

每次任务结束时按当前用户或仓库指令收尾；不要在可公开 skill 中硬编码真实用户称呼。
