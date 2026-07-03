# 风格：城市电台节目单

适合话题跨度大、吐槽和生活内容多的群。整体像城市电台日报节目单，每个成员是节目主持人形象。

```text
Use case: infographic-diagram
Asset type: vertical Chinese WeChat chat summary poster
Primary request: Generate a creative city radio program poster for the WeChat chat "{chat_name}" from {start_date} to {end_date}. This is raster illustration, not HTML and not a screenshot.

Required visible text:
Title: "{chat_name}"
Report name: "{report_name}"
Date line: "{date_line} · {message_count}条消息"
Subtitle: "{subtitle}"

Section 01 title: "今日节目"
Program cards:
1. "{topic_1}"
2. "{topic_2}"
3. "{topic_3}"
4. "{topic_4}"
5. "{topic_5}"
6. "{topic_6}"

Section 02 title: "主播阵容"
Member cards:
{member_cards}

Section 03 title: "收听回放"
Conclusion: "{conclusion}"

Visual style: illustrated radio station schedule, sticker labels, sound waves, microphones, headphones, city-window background, editorial hand-drawn poster. Keep it bright and witty.
Composition: vertical 2:3 poster; station masthead at top; program schedule cards in the center; host avatar cards in 2x4 grid; conclusion ticker at bottom.
Avatar rules: use gender from each member card; no real portraits; subtle gender cues; props can be mic, headphones, cue cards, mixer, calendar, coffee.
Palette: cream, graphite, teal, coral, yellow, green, small blue accents. Avoid purple gradient and dark slate dominance.
Constraints: no data-overview/statistics-overview section, no raw chat logs, no real brand logos, no watermark, no screenshots, concise readable Chinese text.
```
