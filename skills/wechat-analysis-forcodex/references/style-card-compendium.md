# 风格：桌游卡牌图鉴

适合突出群友称号、角色属性和卡牌收藏感。话题像事件卡，群友像可收藏角色卡。

```text
Use case: infographic-diagram
Asset type: vertical Chinese WeChat chat summary poster
Primary request: Generate a creative tabletop card compendium poster for the WeChat chat "{chat_name}" from {start_date} to {end_date}. This is generated raster art, not HTML and not a screenshot.

Required visible text:
Title: "{chat_name}"
Report name: "{report_name}"
Date line: "{date_line} · {message_count}条消息"
Subtitle: "{subtitle}"

Section 01 title: "事件卡"
Event cards:
1. "{topic_1}"
2. "{topic_2}"
3. "{topic_3}"
4. "{topic_4}"
5. "{topic_5}"
6. "{topic_6}"

Section 02 title: "群友卡组"
Member cards:
{member_cards}

Section 03 title: "本局结算"
Conclusion: "{conclusion}"

Visual style: premium illustrated board-game cards on a paper table, hand-drawn icons, small labels, stamp-like rarity marks, playful tactical layout. Do not make it look like a fantasy battle poster.
Composition: vertical 2:3 poster; big title; six event cards in upper half; eight member cards in a neat grid; bottom conclusion as a game-result banner.
Avatar rules: use gender from each member card; no real portraits; each avatar gets role props and a tiny title badge.
Palette: warm paper, black ink, card-white, teal, tomato red, gold, green accents. Avoid one-note dark theme.
Constraints: no data-overview/statistics-overview section, no raw chat logs, no brand logos, no watermark, no screenshots, keep Chinese labels large.
```
