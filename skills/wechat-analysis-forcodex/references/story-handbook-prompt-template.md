# 手帐故事线长图 Prompt 模板

用于把人物/话题故事线总结生成手帐风长图。必须使用 Codex 内置 `image_gen`，不走 HTML 渲染或截图。

## 输入要求

- 先读取 `story_*.md/json`，由 Agent 做语义总结。
- 不要把原始聊天窗口直接铺进图里。
- 图中只放提炼后的节点、称号、关系和结论。
- 对人物使用原创卡通形象；不要画真实头像。

## 模板

```text
Use case: illustration-story
Asset type: long vertical Chinese WeChat story-line handbook poster
Primary request: Generate a hand-drawn scrapbook story timeline for "{target}" in "{chat_name}". This is a generated raster illustration, not HTML rendering and not a screenshot.

Style: Chinese hand帳 / scrapbook poster, warm paper texture, torn tape, stamp labels, highlighter strokes, doodle icons, compact timeline cards, information-rich but clean.

Required visible text:
Title: "{title}"
Subtitle: "{chat_name}｜{date_range}｜{target_message_count}条相关发言/命中"
Badges: "{badge_1}" "{badge_2}" "{badge_3}"

Timeline cards:
01 "{node_1_title}"
body: "{node_1_summary}"
02 "{node_2_title}"
body: "{node_2_summary}"
03 "{node_3_title}"
body: "{node_3_summary}"
04 "{node_4_title}"
body: "{node_4_summary}"
05 "{node_5_title}"
body: "{node_5_summary}"
06 "{node_6_title}"
body: "{node_6_summary}"
Optional nodes if space allows:
07 "{node_7_title}" body: "{node_7_summary}"
08 "{node_8_title}" body: "{node_8_summary}"

Bottom conclusion:
"{conclusion}"

Visual rules:
- Use original small cartoon scenes and props to express each node.
- Do not draw real portraits or imitate real faces.
- Do not show raw chat screenshots, WeChat UI, phone numbers, QR codes, keys, tokens, or private IDs.
- Keep Chinese text short, crisp, high-contrast, and inside card boundaries.

Composition: tall vertical poster, title at top, 6-8 numbered story cards in a winding timeline, bottom conclusion ribbon.
Color palette: warm cream paper, black ink, teal, coral, mustard, green accents. Avoid purple-blue gradient dominance.
```
