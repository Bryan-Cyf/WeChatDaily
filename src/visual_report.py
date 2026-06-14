"""Generate simple visual HTML reports for WeChat group activity."""
import html
import json
import os
import re
from collections import Counter

from paths import REPORTS_DIR


def emoji_count(text):
    return sum(1 for ch in text if ord(ch) >= 0x1F300)


def parse_llm_json(text):
    if not text:
        return None
    match = re.search(r"```json\s*(.*?)```", text, re.S)
    if match:
        text = match.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def build_stats(messages):
    by_hour = Counter(msg["hour"] for msg in messages if msg["hour"] is not None)
    by_sender = Counter(msg["sender"] for msg in messages)
    total_chars = sum(len(msg["text"]) for msg in messages)
    emojis = sum(emoji_count(msg["text"]) for msg in messages)
    active_hour, active_count = (0, 0)
    if by_hour:
        active_hour, active_count = by_hour.most_common(1)[0]
    return {
        "message_count": len(messages),
        "participant_count": len(by_sender),
        "total_characters": total_chars,
        "emoji_count": emojis,
        "hourly": {hour: by_hour.get(hour, 0) for hour in range(24)},
        "most_active_period": f"{active_hour:02d}:00-{(active_hour + 1) % 24:02d}:00" if by_hour else "无",
        "top_users": by_sender.most_common(8),
    }


def html_escape(value):
    return html.escape(str(value), quote=True)


def avatar_hue(name):
    """Stable hue 0-360 from display name."""
    total = sum(ord(ch) for ch in (name or "?"))
    return total % 360


def render_hourly_chart(hourly):
    """Compact vertical bar chart for 24-hour activity."""
    max_count = max(hourly.values()) if hourly else 0
    peak_hour = max(hourly, key=hourly.get) if hourly and max_count else 0
    bars = []
    for hour in range(24):
        count = hourly.get(hour, 0)
        height = 4 if max_count == 0 else max(4, int(count / max_count * 100))
        peak_cls = " peak" if hour == peak_hour and count else ""
        bars.append(
            f'<div class="hour-col{peak_cls}" title="{hour:02d}:00 · {count} 条">'
            f'<div class="hour-bar" style="height:{height}%"></div>'
            f'<span class="hour-count">{count if count else ""}</span>'
            f'<span class="hour-tick">{hour:02d}</span>'
            f"</div>"
        )
    return (
        '<div class="chart-card">'
        '<div class="chart-head"><span>24 小时消息分布</span>'
        f'<em>峰值 {peak_hour:02d}:00–{(peak_hour + 1) % 24:02d}:00</em></div>'
        f'<div class="hour-chart">{"".join(bars)}</div>'
        "</div>"
    )


def render_summary_block(summary):
    if not summary:
        return (
            '<div class="summary-card muted">'
            '<div class="summary-label">今日概览</div>'
            '<p class="summary-text">未进行 AI 总结，可使用 <code>report</code> 命令（不加 <code>--dry-run</code>）生成智能摘要。</p>'
            "</div>"
        )
    return (
        '<div class="summary-card">'
        '<div class="summary-label">AI 今日概览</div>'
        f'<p class="summary-text">{html_escape(summary)}</p>'
        "</div>"
    )


def render_topic_cards(topics):
    if not topics:
        return (
            '<div class="empty-state">'
            "<strong>暂无话题分析</strong>"
            "<span>模型未返回有效话题，或本次使用了 --dry-run。</span>"
            "</div>"
        )

    cards = []
    accents = ("#c2783a", "#2d6a4f", "#3d5a80", "#7b4b94", "#b5451b", "#1d6f8a")
    for idx, topic in enumerate(topics, 1):
        accent = accents[(idx - 1) % len(accents)]
        contributors = topic.get("contributors") or []
        contributor_html = "".join(
            f'<span class="pill">{html_escape(name)}</span>' for name in contributors[:6]
        ) or '<span class="pill muted-pill">未识别</span>'
        time_range = html_escape(topic.get("time_range") or "全天")
        evidence_html = ""
        if topic.get("evidence"):
            quotes = "".join(
                f'<blockquote>{html_escape(item)}</blockquote>'
                for item in topic.get("evidence", [])[:3]
            )
            evidence_html = f'<div class="evidence-block">{quotes}</div>'

        cards.append(
            f'<article class="topic-card" style="--accent:{accent}">'
            f'<div class="topic-index">{idx:02d}</div>'
            '<div class="topic-body">'
            f'<div class="topic-top"><h3>{html_escape(topic.get("topic", "未知话题"))}</h3>'
            f'<span class="time-badge">{time_range}</span></div>'
            f'<div class="contributors">{contributor_html}</div>'
            f'<p class="topic-detail">{html_escape(topic.get("detail", ""))}</p>'
            f"{evidence_html}"
            "</div></article>"
        )
    return f'<div class="topic-list">{"".join(cards)}</div>'


def render_user_cards(user_titles):
    cards = []
    for idx, item in enumerate(user_titles[:8]):
        name = item.get("name") or item.get("user") or "未知"
        title = item.get("title") or "群成员"
        reason = item.get("reason") or ""
        hue = avatar_hue(name)
        initial = html_escape(name[:1] or "?")
        cards.append(
            f'<div class="member-card" style="--hue:{hue}">'
            f'<div class="member-avatar">{initial}</div>'
            '<div class="member-info">'
            f'<div class="member-name">{html_escape(name)}</div>'
            f'<div class="member-title">{html_escape(title)}</div>'
            f'<p>{html_escape(reason)}</p>'
            "</div>"
            f'<div class="member-rank">#{idx + 1}</div>'
            "</div>"
        )
    return f'<div class="member-grid">{"".join(cards)}</div>'


def render_stat_cards(stats):
    items = [
        ("消息总数", stats["message_count"], "条对话记录"),
        ("参与人数", stats["participant_count"], "位群友发言"),
        ("总字符数", stats["total_characters"], "字文本内容"),
        ("表情数量", stats["emoji_count"], "个表情符号"),
    ]
    cards = []
    for label, value, hint in items:
        cards.append(
            f'<div class="metric-card">'
            f'<div class="metric-value">{value:,}</div>'
            f'<div class="metric-label">{html_escape(label)}</div>'
            f'<div class="metric-hint">{html_escape(hint)}</div>'
            "</div>"
        )
    return (
        '<div class="metrics-grid">'
        + "".join(cards)
        + f'<div class="metric-card highlight">'
        f'<div class="metric-value sm">{html_escape(stats["most_active_period"])}</div>'
        f'<div class="metric-label">最活跃时段</div>'
        f'<div class="metric-hint">全天讨论高峰</div>'
        "</div></div>"
    )


def render_top_speakers(stats):
    rows = []
    max_count = stats["top_users"][0][1] if stats["top_users"] else 1
    for name, count in stats["top_users"][:6]:
        width = max(8, int(count / max_count * 100))
        rows.append(
            f'<div class="speaker-row">'
            f'<span class="speaker-name">{html_escape(name)}</span>'
            f'<div class="speaker-bar-wrap"><div class="speaker-bar" style="width:{width}%"></div></div>'
            f'<span class="speaker-count">{count}</span>'
            "</div>"
        )
    if not rows:
        return ""
    return (
        '<div class="side-card">'
        "<h3>发言排行</h3>"
        f'{"".join(rows)}'
        "</div>"
    )


def render_html_report(group_name, date_str, messages, analysis=None, output_path=None):
    stats = build_stats(messages)
    analysis = analysis or {}
    topics = analysis.get("topics") or []
    user_titles = analysis.get("user_titles") or []
    summary = analysis.get("summary") or ""

    if not user_titles:
        user_titles = [
            {
                "name": name,
                "title": "话痨本痨" if idx == 0 else "气氛组",
                "reason": f"今日发言 {count} 条",
            }
            for idx, (name, count) in enumerate(stats["top_users"])
        ]

    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    try:
        from datetime import datetime
        weekday = weekday_names[datetime.strptime(date_str, "%Y-%m-%d").weekday()]
    except ValueError:
        weekday = ""

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_escape(group_name)} · 群聊日报 {date_str}</title>
  <style>
    :root {{
      --bg: #ece8df;
      --paper: #fffdf8;
      --ink: #1c1917;
      --ink-soft: #57534e;
      --line: rgba(28, 25, 23, 0.08);
      --gold: #b8860b;
      --gold-soft: #f4e8c8;
      --teal: #1f6f5f;
      --shadow: 0 24px 60px rgba(28, 25, 23, 0.12);
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at 12% 8%, rgba(184, 134, 11, 0.18), transparent 28%),
        radial-gradient(circle at 88% 0%, rgba(31, 111, 95, 0.14), transparent 24%),
        linear-gradient(180deg, #e8e2d6 0%, var(--bg) 100%);
      line-height: 1.6;
    }}
    .shell {{
      width: min(1120px, calc(100vw - 32px));
      margin: 28px auto 48px;
    }}
    .report {{
      background: var(--paper);
      border: 1px solid rgba(255,255,255,0.7);
      border-radius: calc(var(--radius) + 6px);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .hero {{
      position: relative;
      padding: 42px 40px 34px;
      color: #faf7f0;
      background:
        linear-gradient(135deg, rgba(255,255,255,0.06), transparent 40%),
        linear-gradient(120deg, #1f2937 0%, #111827 45%, #1f6f5f 100%);
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -10% -40% auto;
      width: 320px;
      height: 320px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(184,134,11,0.35), transparent 68%);
      pointer-events: none;
    }}
    .hero-badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 12px;
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 999px;
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      background: rgba(255,255,255,0.08);
      backdrop-filter: blur(8px);
    }}
    .hero-badge::before {{
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #fbbf24;
      box-shadow: 0 0 12px rgba(251, 191, 36, 0.8);
    }}
    .hero h1 {{
      margin: 18px 0 8px;
      font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", "SimSun", serif;
      font-size: clamp(28px, 4vw, 42px);
      font-weight: 700;
      letter-spacing: 0.02em;
      line-height: 1.15;
    }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 18px;
      color: rgba(250, 247, 240, 0.82);
      font-size: 14px;
    }}
    .hero-meta span {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .hero-meta span::before {{
      content: "•";
      color: var(--gold);
    }}
    .hero-meta span:first-child::before {{ content: none; }}
    .content {{ padding: 28px 34px 36px; }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 280px;
      gap: 22px;
      align-items: start;
    }}
    .main-col {{ display: grid; gap: 22px; min-width: 0; }}
    .section-title {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 0 0 14px;
      font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", serif;
      font-size: 20px;
      font-weight: 700;
    }}
    .section-title::before {{
      content: "";
      width: 4px;
      height: 18px;
      border-radius: 99px;
      background: linear-gradient(180deg, var(--gold), var(--teal));
    }}
    .summary-card {{
      padding: 22px 24px;
      border-radius: var(--radius);
      background: linear-gradient(180deg, #fff9eb 0%, #fffdf8 100%);
      border: 1px solid #f0dfae;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.8);
    }}
    .summary-card.muted {{
      background: #f8f7f4;
      border-color: var(--line);
    }}
    .summary-label {{
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.12em;
      color: var(--gold);
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    .summary-text {{
      margin: 0;
      font-size: 16px;
      line-height: 1.85;
      color: #292524;
    }}
    .summary-text code {{
      font-size: 12px;
      padding: 2px 6px;
      border-radius: 6px;
      background: rgba(28,25,23,0.06);
    }}
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
    }}
    .metric-card {{
      padding: 18px 14px;
      border-radius: 16px;
      background: #faf9f6;
      border: 1px solid var(--line);
      text-align: center;
    }}
    .metric-card.highlight {{
      background: linear-gradient(160deg, #173f38, #1f6f5f);
      color: #f5fffb;
      border-color: transparent;
    }}
    .metric-value {{
      font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", serif;
      font-size: 28px;
      font-weight: 700;
      line-height: 1.1;
    }}
    .metric-value.sm {{ font-size: 22px; }}
    .metric-label {{
      margin-top: 8px;
      font-size: 13px;
      font-weight: 700;
    }}
    .metric-hint {{
      margin-top: 4px;
      font-size: 11px;
      opacity: 0.72;
    }}
    .chart-card {{
      padding: 18px 18px 12px;
      border-radius: var(--radius);
      border: 1px solid var(--line);
      background: #fcfbfa;
    }}
    .chart-head {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 14px;
      font-size: 13px;
      color: var(--ink-soft);
    }}
    .chart-head span {{ font-weight: 700; color: var(--ink); font-size: 14px; }}
    .hour-chart {{
      display: grid;
      grid-template-columns: repeat(24, minmax(0, 1fr));
      gap: 4px;
      align-items: end;
      height: 160px;
      padding-top: 8px;
    }}
    .hour-col {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: end;
      height: 100%;
      gap: 4px;
    }}
    .hour-bar {{
      width: 100%;
      max-width: 18px;
      border-radius: 8px 8px 4px 4px;
      background: linear-gradient(180deg, #64748b, #334155);
      min-height: 4px;
      transition: transform 0.2s ease;
    }}
    .hour-col.peak .hour-bar {{
      background: linear-gradient(180deg, #fbbf24, #b8860b);
      box-shadow: 0 0 16px rgba(184, 134, 11, 0.35);
    }}
    .hour-count {{
      font-size: 9px;
      color: var(--ink-soft);
      min-height: 12px;
    }}
    .hour-tick {{
      font-size: 9px;
      color: #a8a29e;
    }}
    .topic-list {{ display: grid; gap: 14px; }}
    .topic-card {{
      display: grid;
      grid-template-columns: 54px minmax(0, 1fr);
      gap: 14px;
      padding: 18px 18px 18px 0;
      border-radius: var(--radius);
      background: #fff;
      border: 1px solid var(--line);
      box-shadow: 0 8px 24px rgba(28,25,23,0.04);
    }}
    .topic-index {{
      display: flex;
      align-items: center;
      justify-content: center;
      margin-left: 18px;
      height: 54px;
      border-radius: 14px;
      background: color-mix(in srgb, var(--accent) 12%, white);
      color: var(--accent);
      font-family: "Source Han Serif SC", "Noto Serif SC", serif;
      font-size: 18px;
      font-weight: 700;
    }}
    .topic-top {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
    }}
    .topic-top h3 {{
      margin: 0;
      font-size: 17px;
      line-height: 1.35;
    }}
    .time-badge {{
      padding: 4px 10px;
      border-radius: 999px;
      background: #f5f5f4;
      color: var(--ink-soft);
      font-size: 12px;
      white-space: nowrap;
    }}
    .contributors {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 10px;
    }}
    .pill {{
      padding: 4px 10px;
      border-radius: 999px;
      background: color-mix(in srgb, var(--accent) 10%, white);
      border: 1px solid color-mix(in srgb, var(--accent) 22%, white);
      color: #44403c;
      font-size: 12px;
    }}
    .pill.muted-pill {{ background: #f5f5f4; border-color: #e7e5e4; color: #78716c; }}
    .topic-detail {{
      margin: 0;
      color: #44403c;
      font-size: 14px;
      line-height: 1.75;
    }}
    .evidence-block {{
      margin-top: 12px;
      display: grid;
      gap: 8px;
    }}
    .evidence-block blockquote {{
      margin: 0;
      padding: 10px 12px 10px 14px;
      border-left: 3px solid var(--accent);
      border-radius: 0 10px 10px 0;
      background: #fafaf9;
      color: #57534e;
      font-size: 13px;
    }}
    .member-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .member-card {{
      position: relative;
      display: grid;
      grid-template-columns: 52px minmax(0, 1fr);
      gap: 12px;
      padding: 16px;
      border-radius: 16px;
      background: linear-gradient(135deg, #fff, #faf9f6);
      border: 1px solid var(--line);
      overflow: hidden;
    }}
    .member-card::after {{
      content: "";
      position: absolute;
      inset: 0 auto 0 0;
      width: 4px;
      background: hsl(var(--hue), 55%, 48%);
    }}
    .member-avatar {{
      width: 52px;
      height: 52px;
      border-radius: 16px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 18px;
      color: white;
      background: linear-gradient(135deg, hsl(var(--hue), 62%, 52%), hsl(calc(var(--hue) + 24), 58%, 38%));
      box-shadow: 0 10px 20px hsla(var(--hue), 50%, 40%, 0.25);
    }}
    .member-name {{ font-weight: 800; font-size: 15px; }}
    .member-title {{
      display: inline-block;
      margin: 6px 0;
      padding: 3px 8px;
      border-radius: 8px;
      background: #fef3c7;
      color: #92400e;
      font-size: 12px;
      font-weight: 700;
    }}
    .member-info p {{
      margin: 0;
      color: var(--ink-soft);
      font-size: 12px;
      line-height: 1.5;
    }}
    .member-rank {{
      position: absolute;
      top: 12px;
      right: 12px;
      font-size: 11px;
      font-weight: 700;
      color: #d6d3d1;
    }}
    .side-card {{
      padding: 18px;
      border-radius: var(--radius);
      background: #faf9f6;
      border: 1px solid var(--line);
    }}
    .side-card h3 {{
      margin: 0 0 14px;
      font-size: 15px;
    }}
    .speaker-row {{
      display: grid;
      grid-template-columns: 72px 1fr 34px;
      gap: 8px;
      align-items: center;
      margin-bottom: 10px;
      font-size: 12px;
    }}
    .speaker-name {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--ink-soft);
    }}
    .speaker-bar-wrap {{
      height: 8px;
      border-radius: 99px;
      background: #ece9e4;
      overflow: hidden;
    }}
    .speaker-bar {{
      height: 100%;
      border-radius: 99px;
      background: linear-gradient(90deg, var(--teal), #34d399);
    }}
    .speaker-count {{ text-align: right; font-weight: 700; color: var(--ink); }}
    .empty-state {{
      padding: 28px;
      border-radius: var(--radius);
      border: 1px dashed #d6d3d1;
      background: #fafaf9;
      text-align: center;
      color: var(--ink-soft);
    }}
    .empty-state strong {{
      display: block;
      margin-bottom: 6px;
      color: var(--ink);
      font-size: 15px;
    }}
    footer {{
      padding: 18px 34px 24px;
      border-top: 1px solid var(--line);
      color: #a8a29e;
      font-size: 12px;
      text-align: center;
      background: #fcfbfa;
    }}
    @media (max-width: 920px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .metrics-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .member-grid {{ grid-template-columns: 1fr; }}
      .hero, .content {{ padding-left: 22px; padding-right: 22px; }}
    }}
    @media (max-width: 560px) {{
      .metrics-grid {{ grid-template-columns: 1fr; }}
      .topic-card {{ grid-template-columns: 1fr; }}
      .topic-index {{ margin: 0 18px; width: fit-content; min-width: 54px; }}
      .hour-chart {{ height: 120px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <article class="report">
      <header class="hero">
        <div class="hero-badge">WeChat Daily Insight</div>
        <h1>{html_escape(group_name)}</h1>
        <div class="hero-meta">
          <span>{html_escape(date_str)}{(" · " + weekday) if weekday else ""}</span>
          <span>{stats["message_count"]:,} 条消息</span>
          <span>{stats["participant_count"]} 人参与</span>
        </div>
      </header>

      <div class="content">
        {render_summary_block(summary)}

        <div class="layout">
          <div class="main-col">
            <section>
              <h2 class="section-title">数据概览</h2>
              {render_stat_cards(stats)}
            </section>

            <section>
              {render_hourly_chart(stats["hourly"])}
            </section>

            <section>
              <h2 class="section-title">热门话题</h2>
              {render_topic_cards(topics)}
            </section>

            <section>
              <h2 class="section-title">群友称号</h2>
              {render_user_cards(user_titles)}
            </section>
          </div>

          <aside>
            {render_top_speakers(stats)}
          </aside>
        </div>
      </div>

      <footer>Generated by WeChatDaily · 数据来自本地解密数据库 · AI 话题由 Agent 结构化分析</footer>
    </article>
  </div>
</body>
</html>"""

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_text)
    return html_text


def find_font():
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def draw_wrapped(draw, xy, text, font, fill, max_width, line_gap=6):
    x, y = xy
    lines = []
    for raw_line in str(text).splitlines() or [""]:
        current = ""
        for ch in raw_line:
            trial = current + ch
            if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += draw.textbbox((0, 0), line, font=font)[3] + line_gap
    return y


def render_html_to_png(html_path, png_path, width=1180):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "未安装 Python Playwright：pip install playwright"

    html_url = "file:///" + os.path.abspath(html_path).replace(os.sep, "/")
    launch_attempts = [
        {"name": "chromium", "kwargs": {}},
        {"name": "msedge", "kwargs": {"channel": "msedge"}},
        {"name": "chrome", "kwargs": {"channel": "chrome"}},
    ]
    last_error = ""

    try:
        with sync_playwright() as p:
            browser = None
            for attempt in launch_attempts:
                try:
                    launcher = getattr(p, attempt["name"])
                    browser = launcher.launch(**attempt["kwargs"])
                    break
                except Exception as e:
                    last_error = str(e)
                    browser = None
            if browser is None:
                return False, (
                    "无法启动浏览器截图。请安装 Chromium：python -m playwright install chromium；"
                    "或确保本机已安装 Edge/Chrome。"
                )

            page = browser.new_page(viewport={"width": width, "height": 1600}, device_scale_factor=1)
            page.goto(html_url, wait_until="networkidle")
            height = page.evaluate("document.documentElement.scrollHeight")
            page.set_viewport_size({"width": width, "height": height})
            os.makedirs(os.path.dirname(png_path), exist_ok=True)
            page.screenshot(path=png_path, full_page=True)
            browser.close()
        if os.path.exists(png_path):
            return True, ""
        return False, "Playwright 执行完成，但 PNG 文件未生成"
    except Exception as e:
        msg = str(e) or last_error
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            return False, "缺少 Chromium：python -m playwright install chromium"
        return False, msg[:300]
