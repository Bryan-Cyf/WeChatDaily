"""Render HTML report from markdown chat log + Agent analysis JSON."""
import argparse
import json
import os
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from paths import REPORTS_DIR
from visual_report import render_html_report

ANALYSIS_REGISTRY = {}

ANALYSIS_2026_06_04_STOCK = {
    "summary": (
        "周四群聊围绕美股大跌后的 A 股开盘展开，早盘 MLCC/科技线集体走强，"
        "成员高频讨论卖飞、T 飞与拿不住的心态问题；午后转向电力/PCB 板块轮动与龙头战法，"
        "收盘互晒收益并调侃「献祭邹总换涨停」；晚间延续个股复盘，并深入讨论 MLCC 概念辨析、"
        "算力租赁与国产卡逻辑。"
    ),
    "topics": [
        {
            "topic": "美股大跌与早盘竞价情绪",
            "time_range": "08:50-09:16",
            "contributors": ["小米邹", "Peter", "ㅤ", "梦里花落", "DDZ", "丁大胖"],
            "detail": (
                "小米邹分析隔夜美股回调原因（地缘、通胀、降息预期），Peter 称已减持美股；"
                "群友预判 A 股可能跟跌，竞价前讨论通富能否续板、科技是否「骗炮」，开盘初期多数个股偏绿。"
            ),
            "evidence": [
                "昨天晚上美股 什么跌的这么惨？",
                "大A随的份子会比美股跌的多，感觉",
                "紧张刺激的竞价时刻 马上到了",
            ],
        },
        {
            "topic": "MLCC 与双星等科技股早盘爆发",
            "time_range": "09:16-10:00",
            "contributors": ["帐篷", "Peter", "小米邹", "Francis", "梦里花落", "ㅤ", "丁大胖"],
            "detail": (
                "开盘后出现双星、大为、江海、三安、通鼎、京东方等强势拉升，MLCC 板块成为主线；"
                "帐篷强调趋势与大盘股逻辑，Peter 多次过早卖出后懊悔，群聊形成「不亏钱才是重点」的共识。"
            ),
            "evidence": ["双星  NB", "直接涨停了", "mlcc牛批"],
        },
        {
            "topic": "卖飞、T 飞与交易心态",
            "time_range": "09:38-12:04",
            "contributors": ["Peter", "帐篷", "ㅤ", "梦里花落", "Francis"],
            "detail": (
                "Peter 双星八个多点卖出后涨停，ㅤ 小江 T 飞，多人感叹「拿不住就是挖地抓鱼」；"
                "帐篷劝买两三百亿以上大盘股、别瞎做 T，DDZ 补充只做上涨趋势更安全。"
            ),
            "evidence": ["我少吃16个点", "我小江T飞了", "拿不住就是挖地"],
        },
        {
            "topic": "板块轮动：电力、煤炭与跷跷板",
            "time_range": "10:15-14:30",
            "contributors": ["DDZ", "帐篷", "ㅤ", "Peter", "梦里花落", "丁大胖"],
            "detail": (
                "科技强时群友讨论埋伏电力/煤炭的跷跷板策略；丁大胖称 MLCC 与电力「目前无敌」；"
                "午后多人布局可立克与电力股，帐篷分析电力季节性与枯水期火电逻辑。"
            ),
            "evidence": [
                "跷跷板，今天涨科技，就埋伏电力煤炭",
                "MLCC 电力 这两个目前无敌",
                "4-5-6-7月上旬都是枯水季",
            ],
        },
        {
            "topic": "龙头战法与可立克买点",
            "time_range": "13:30-16:21",
            "contributors": ["DDZ", "Peter", "ㅤ", "梦里花落", "帐篷"],
            "detail": (
                "DDZ 分享「龙头首阴战法」及可立克「跳空低开倒锤线」买点；"
                "Peter 表示要跟单，ㅤ 从射击之星形态解释买入可立克，群友约定拿住观察是否跌破。"
            ),
            "evidence": [
                "龙头首阴战法 最近胜率极高",
                "今天的可立克就是她战法的一个买点",
                "感觉有了个底部射击之星，可以买",
            ],
        },
        {
            "topic": "收盘复盘与群内收益互晒",
            "time_range": "15:00-16:10",
            "contributors": ["Peter", "小米邹", "帐篷", "ㅤ", "梦里花落", "丁大胖"],
            "detail": (
                "收盘前后群友互道「希望明天吃肉」，Peter 畅想群内谁率先炒出 100 万；"
                "小米邹自曝 6 月收益仅 +33 元，引发调侃；多人晒当日微利或卖飞遗憾。"
            ),
            "evidence": ["希望明天吃肉", "6月收益  +33", "33块"],
        },
        {
            "topic": "季节板块日历与「窄牛」市场观",
            "time_range": "15:52-16:10",
            "contributors": ["帐篷", "丁大胖", "DDZ", "ㅤ"],
            "detail": (
                "帐篷归纳全年炒作节奏（年初电力、七八月 PCB、九十月旅游、年底消费）；"
                "群友讨论当前「窄牛」——少数大票新高、散户难赚。"
            ),
            "evidence": ["七八月份炒PCB", "专业名词：窄牛", "生怕散户赚钱"],
        },
        {
            "topic": "MLCC 概念辨析与个股归属",
            "time_range": "20:04-20:13",
            "contributors": ["Francis", "帐篷", "Peter"],
            "detail": (
                "Francis 追问 MLCC 是否等于电容、亨通与 CPO/光通信关系；"
                "厘清风华高科才有 MLCC，江海/法拉走电容线，双星属材料。"
            ),
            "evidence": ["mlcc不是电容", "风华高科官网有这个", "双星是材料"],
        },
        {
            "topic": "算力租赁与国产卡逻辑",
            "time_range": "20:57-21:19",
            "contributors": ["DDZ", "Peter", "Francis", "ㅤ", "梦里花落"],
            "detail": (
                "DDZ 讨论算电协同、B300 卡价暴涨、国产卡效率与「算力租赁黄金坑」；"
                "认为电炒完后可能轮到算力，Peter 表示跟随大哥、少频繁换股。"
            ),
            "evidence": [
                "算力租赁马上是黄金坑了",
                "B300的价格今天是1000万",
                "等这波电炒完，估计就该轮到算力了",
            ],
        },
    ],
    "user_titles": [
        {
            "name": "Peter",
            "title": "卖飞慈善家",
            "reason": "全天最高频发言，多次过早卖出后反复懊悔，自称「选股没问题，技术问题」。",
        },
        {
            "name": "帐篷",
            "title": "趋势布道者",
            "reason": "持续输出 MLCC/电力/大盘股逻辑与季节板块日历，是被 @ 最多的意见领袖。",
        },
        {
            "name": "DDZ",
            "title": "模式流大师",
            "reason": "分享龙头首阴、可立克倒锤线买点及算力/card 宏观判断，多人称「跟着大哥」。",
        },
        {
            "name": "ㅤ",
            "title": "T 飞体验官",
            "reason": "小江 T 飞、翻倍踏空等「卖完就涨」案例集中，同时布局可立克与电力。",
        },
        {
            "name": "Francis",
            "title": "概念课代表",
            "reason": "追问 MLCC/CPO/光通信区别，分享北部湾涨停转跌停的惨痛经历。",
        },
        {
            "name": "小米邹",
            "title": "通富守望者",
            "reason": "早盘播报竞价与板块，收盘自曝月收益 33 元成为群聊名场面。",
        },
        {
            "name": "梦里花落",
            "title": "听劝实干派",
            "reason": "跟进可立克等建议，常用「往事不可追」安慰卖飞党。",
        },
        {
            "name": "丁大胖",
            "title": "荐股活雷锋",
            "reason": "推票常自己不买，中旭激励计划「35 到 1280」引发群友集体酸了。",
        },
    ],
}

ANALYSIS_2026_06_04_DOTNET = {
    "summary": (
        "周四以生活向闲聊为主：上午从婚恋成家、内求外求聊到「此群要诞生第一对」；"
        "中段刷屏脑筋急转弯/成语猜谜与 AI 离谱回答；穿插 cc-switch 同步、Java 转 C# 工控等少量技术点；"
        "ABCD 发起防晒与颈纹护肤长讨论；下午河北冰雹、山河四省高校与大盘吐槽；"
        "傍晚 MiniMax 评测、身高体重接龙与关关长语晒硬核晚餐收束。"
    ),
    "topics": [
        {
            "topic": "婚恋观与成家焦虑",
            "time_range": "08:16-09:30",
            "contributors": ["子明。", "Francis", "槑子", "Mr Li", "丁大胖", "小奇"],
            "detail": (
                "Francis 讨论婚姻/育儿「牢笼论」，子明表达成家欲望与武汉买房顾虑；"
                "群友互开玩笑「借 10W 结婚」「此群要诞生第一对」，Bryan 分享无房无车娶到四川媳妇经历。"
            ),
            "evidence": [
                "目前确实有成家得欲望",
                "怎么说？此群要诞生第一对？",
                "我老家没房，没车。还不是能娶到媳妇",
            ],
        },
        {
            "topic": "脑筋急转弯与成语猜谜",
            "time_range": "09:49-11:10",
            "contributors": ["小奇", "亚坤", "北海", "😘😘包子", "小邹", "丁大胖"],
            "detail": (
                "小奇连续出「侄子/爸爸」等 AI 猜题梗，群友自嘲文盲；"
                "随后成语/谐音梗游戏爆发（家徒四壁、天网恢恢、匪夷所思、人老珠黄等），抢答氛围极浓。"
            ),
            "evidence": [
                "感觉自己像个文盲",
                "都侄子了，还能爸爸",
                "人老珠黄",
            ],
        },
        {
            "topic": "技术片段：C# 工控与 cc-switch",
            "time_range": "10:10-10:11",
            "contributors": ["子明。", "北海", "亚坤"],
            "detail": (
                "子明提到同学从 Java 转 C# 做工控，北海调侃「C# 又有春天」；"
                "亚坤询问 cc-switch 的 WebDAV 同步另一台机器下载为空的问题，是当日少有的纯技术提问。"
            ),
            "evidence": [
                "要转c#  工控了",
                "C#又有春天了？",
                "cc-switch  webdav同步你们用了吗",
            ],
        },
        {
            "topic": "防晒护肤与 AI 种草",
            "time_range": "10:38-11:30",
            "contributors": ["ABCD", "槑子", "😘😘包子", "北海", "游僧"],
            "detail": (
                "ABCD 向群姐妹求推荐防晒霜；槑子推蜜丝婷，北海用 AI 搜美白产品被 ABCD 指出含广告；"
                "讨论物理防晒/冰袖、李佳琦直播间、欧莱雅与卸妆流程，618 比价成共识。"
            ),
            "evidence": [
                "哪一款的防晒霜效果最好",
                "给AI灌了广告进去了",
                "物理防晒最好，买冰袖",
            ],
        },
        {
            "topic": "男生护肤与颈纹讨论",
            "time_range": "12:28-13:20",
            "contributors": ["ABCD", "槑子", "误", "😘😘包子", "So"],
            "detail": (
                "ABCD 追问颈纹淡化与珀莱雅盾护，甚至搜美团玻尿酸项目；"
                "槑子提醒别自己打针要去实体店，误调侃「是不是被富婆包养」引发男生爱美之辩。"
            ),
            "evidence": [
                "有没有淡化颈纹的产品姐妹们",
                "别自己买针打",
                "男生爱美怎么了",
            ],
        },
        {
            "topic": "学术打假与 AI Agent 时长",
            "time_range": "10:18-10:56",
            "contributors": ["勤古James", "张巍（晚十一点睡觉）", "ABCD"],
            "detail": (
                "勤古James 转发耿同学打假博导、学术造假话题；"
                "张巍感叹 AI Agent 执行从十几二十分钟提升到常跑 1–2 小时，ABCD 提醒部分内容为广告。"
            ),
            "evidence": [
                "你看耿同学打假博导了吗",
                "现在执行1-2个小时好像家常便饭了",
                "这个是广告",
            ],
        },
        {
            "topic": "河北冰雹与山河四省高校",
            "time_range": "14:31-15:01",
            "contributors": ["玩命小卒", "勤古James", "😘😘包子", "亚坤", "游僧"],
            "detail": (
                "玩命小卒在保定遭遇突发冰雹+彩虹，群友插科打诨「六月飞霜」；"
                "话题转向山河四省 985/211 分布与人才外流，游僧一句「科技不死，大 A 不兴」带偏到股市。"
            ),
            "evidence": [
                "下雹子了",
                "山河四省加一起也只有2所",
                "科技不死，大A不兴",
            ],
        },
        {
            "topic": "MiniMax 吐槽与身高体重接龙",
            "time_range": "16:35-21:30",
            "contributors": ["DDZ", "KeepYoung", "关关长语", "子明。", "小奇", "空"],
            "detail": (
                "DDZ 评价 MiniMax M3.0「蠢如猪」；傍晚群友接龙身高 185/188 与体重 120/140；"
                "关关长语晒小米辣+泡椒晚餐，KeepYoung 调侃「辣椒炒小米椒」「菊花火葬场」。"
            ),
            "evidence": [
                "minimax M3.0 蠢如猪，鉴定完毕",
                "188三次",
                "小米辣 泡椒 泡萝卜 泡姜",
            ],
        },
    ],
    "user_titles": [
        {
            "name": "子明。",
            "title": "想成家胖虎",
            "reason": "全天多次表达成家欲望与内求觉悟，自称胖虎/180，是婚恋话题核心人物。",
        },
        {
            "name": "小奇",
            "title": "谜题出题官",
            "reason": "连续发布 AI 脑筋急转弯与猜成语梗，带动上午最活跃的娱乐讨论。",
        },
        {
            "name": "ABCD",
            "title": "精致护肤Boy",
            "reason": "主动发起防晒、颈纹、玻尿酸等护肤长帖，打破「程序员不防晒」刻板印象。",
        },
        {
            "name": "槑子",
            "title": "生活百科姐",
            "reason": "蜜丝婷/物理防晒/医美风险提示等实用建议输出最多，还顺带聊育儿累并预期内。",
        },
        {
            "name": "亚坤",
            "title": "成语抢答王",
            "reason": "在猜谜环节高频抢答「匪夷所思」等，也抛出 cc-switch 技术问题。",
        },
        {
            "name": "😘😘包子",
            "title": "姐妹话事人",
            "reason": "护肤讨论中代表「物理防晒派」，多次纠正男德/已婚边界，气氛组担当。",
        },
        {
            "name": "玩命小卒",
            "title": "冰雹现场记者",
            "reason": "实时播报河北保定冰雹、彩虹与天气突变，引发山河四省高校延伸聊。",
        },
        {
            "name": "勤古James",
            "title": "吃瓜播报员",
            "reason": "耿同学打假、贾佛段子、卷到 9 点等话题的多线输出者。",
        },
    ],
}

ANALYSIS_REGISTRY["涨停发财群"] = ANALYSIS_2026_06_04_STOCK
ANALYSIS_REGISTRY["全球Dotnet技术交流总群"] = ANALYSIS_2026_06_04_DOTNET


def resolve_md_path(date_str, group_name, md_path=None):
    if md_path:
        return Path(md_path)
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in group_name)[:60]
    per_group = Path(REPORTS_DIR) / f"report_{date_str}_{safe_name}.md"
    if per_group.exists():
        return per_group
    combined = Path(REPORTS_DIR) / f"report_{date_str}.md"
    if combined.exists():
        return combined
    raise SystemExit(f"未找到报告文件: {per_group} 或 {combined}")


def extract_group_section(text, group_name):
    lines = text.splitlines()
    section_lines = []
    in_section = False
    found_heading = False
    for line in lines:
        if line.startswith("## "):
            found_heading = True
            if in_section:
                break
            in_section = line[3:].strip() == group_name
            continue
        if not in_section and line.startswith("# ") and group_name in line:
            in_section = True
            continue
        if in_section:
            if line.strip() == "---":
                break
            section_lines.append(line)
    if section_lines:
        return "\n".join(section_lines)
    if found_heading:
        return ""
    return text


def parse_md_chat(md_path, group_name=None):
    text = Path(md_path).read_text(encoding="utf-8")
    if group_name and "## " in text:
        scoped = extract_group_section(text, group_name)
        if not scoped:
            return []
        text = scoped
    in_block = False
    messages = []
    line_re = re.compile(r"^\[(\d{2}:\d{2})\] ([^:]+): (.*)$")
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip() == "```":
            in_block = not in_block
            continue
        if not in_block:
            continue
        m = line_re.match(line.strip())
        if not m:
            continue
        time_text, sender, body = m.groups()
        hour = int(time_text.split(":")[0])
        messages.append(
            {
                "time_text": time_text,
                "hour": hour,
                "sender": sender.strip(),
                "text": body.strip(),
            }
        )
    return messages


def main():
    parser = argparse.ArgumentParser(description="从 MD 聊天记录 + 手工分析生成 HTML 日报")
    parser.add_argument("--md", help="report_YYYY-MM-DD.md 或 report_YYYY-MM-DD_群名.md 路径；不传则自动查找")
    parser.add_argument("--group", required=True, help="群显示名")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--analysis-json", help="结构化分析 JSON 文件（summary/topics/user_titles）")
    parser.add_argument("-o", help="输出 HTML 路径，默认 export/reports/report_{date}_{group}.html")
    parser.add_argument("--png", action="store_true", help="同时导出 PNG（需 playwright chromium）")
    args = parser.parse_args()

    md_path = resolve_md_path(args.date, args.group, args.md)
    messages = parse_md_chat(md_path, args.group)
    if not messages:
        raise SystemExit(f"未能从 {md_path} 解析到群「{args.group}」的聊天记录")

    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in args.group)[:60]
    output = args.o or os.path.join(REPORTS_DIR, f"report_{args.date}_{safe_name}.html")

    if args.analysis_json:
        with open(args.analysis_json, encoding="utf-8") as f:
            analysis = json.load(f)
    else:
        analysis = ANALYSIS_REGISTRY.get(args.group)
        if not analysis:
            known = "、".join(ANALYSIS_REGISTRY) or "（无）"
            raise SystemExit(
                f"未找到群「{args.group}」的内置分析，请传 --analysis-json。内置支持: {known}"
            )

    render_html_report(args.group, args.date, messages, analysis, output)
    print(f"messages={len(messages)}")
    print(f"html={output}")

    if args.png:
        from visual_report import render_html_to_png

        png_path = os.path.splitext(output)[0] + ".png"
        ok, reason = render_html_to_png(output, png_path)
        if ok:
            print(f"png={png_path}")
        else:
            raise SystemExit(f"PNG 生成失败: {reason}")


if __name__ == "__main__":
    main()
