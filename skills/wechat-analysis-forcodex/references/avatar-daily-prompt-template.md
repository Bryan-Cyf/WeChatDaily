# 手账角色卡日报 Prompt 模板

用于通过 Codex 内置 `image_gen` 生成微信聊天日报图片。该模板是日报默认风格，参考手绘纸张、毛笔标题、编号话题卡和群友角色卡；不要生成 HTML 后截图。

## 输入要求

- 从导出的 `stats_*.json` 读取 `message_count`、`top_senders`、`speaker_profiles`。
- `speaker_profiles[*].gender` 必须来自微信联系人数据；只接受 `male`、`female`、`unknown`。
- 能从微信读取性别时必须使用微信性别；`unknown` 时使用中性小像，不要按名字猜。
- 称号和话题由 Agent 读取聊天记录后总结，保持简短，不做人身攻击。

## 模板

```text
Use case: infographic-diagram
Asset type: vertical Chinese WeChat daily summary poster
Primary request: Generate a hand-drawn daily report poster for the WeChat chat "{chat_name}" on {date}. This is a generated raster illustration, not HTML rendering and not a screenshot.

Style reference: Chinese hand-drawn notebook poster, brush calligraphy headline, cream paper texture, marker outlines, numbered topic cards, stamp labels, compact member role cards, information-rich but organized.

Required visible text:
Title: "{chat_name}"
Report name: "{report_name}"
Date line: "{date} · {message_count}条消息"
Subtitle: "{subtitle}"

Section 01 title: "热门话题"
Topic cards:
1. "{topic_1}"
2. "{topic_2}"
3. "{topic_3}"
4. "{topic_4}"
5. "{topic_5}"
6. "{topic_6}"
Optional topic cards if space allows:
7. "{topic_7}"
8. "{topic_8}"

Section 02 title: "群友角色卡"
Member cards:
{member_cards}

Section 03 title: "今日结论"
Conclusion: "{conclusion}"

Member avatar rules:
- Every member card must include one small original chibi cartoon avatar, the member name, and the short title.
- Do not draw real portraits or imitate real faces.
- For gender=male, use a masculine but not stereotyped avatar.
- For gender=female, use a feminine but not stereotyped avatar.
- For gender=unknown, use a clearly neutral avatar.
- Show gender through subtle hair shape, clothing silhouette, expression, and props; do not use exaggerated body traits.
- Prioritize each role prop over appearance: pointer, wrench, speech horn, blueprint, chat bubble, telescope, document folder, radar display, keyboard, shield, magnifier.

Composition/framing: vertical 2:3 poster. Large brush title at top; topic cards in the upper-middle; member avatar cards in a tidy grid in the lower-middle; conclusion ribbon at the bottom. Dense enough for a daily report, but keep all labels short and legible.

Color palette: warm cream paper, black ink, teal, orange, vermilion, green, yellow highlights. Avoid purple-blue gradient dominance.

Constraints: no data-overview/statistics-overview section or title, no raw chat logs, no phone numbers, no private keys, no QR codes, no real WeChat logo, no screenshots, no watermark, no brand logos. Chinese text should be crisp, correctly spelled, high-contrast, and not clipped.
```

## member_cards 写法

每行一个成员，格式固定：

```text
- "{name}｜{title}｜{message_count}条｜gender={gender}｜avatar prop={prop}"
```

示例：

```text
- "张倩｜今日主讲人｜159条｜gender=female｜avatar prop=microphone and pointer"
- "亚坤｜AI实操补丁工｜133条｜gender=male｜avatar prop=wrench and terminal"
- "mango｜气氛转场王｜108条｜gender=unknown｜avatar prop=sparkle chat bubble"
```
