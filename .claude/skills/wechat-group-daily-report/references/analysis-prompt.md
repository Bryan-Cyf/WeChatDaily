# 群聊结构化分析 Prompt（Agent 必读）

执行本 Skill 时，**由当前 Agent 充当分析器**。项目不内置 LLM，勿尝试调用任何 API Key 驱动的分析接口。

对每个群，从 `export/reports/report_{date}.md` 中该群的「聊天记录」代码块读取全文，填入下方模板中的 `{messages_text}`，按规则输出**纯 JSON**。

## Prompt 模板

```
你是群聊日报分析器。请分析微信群「{group_name}」在 {date_str} 的聊天记录。

只输出 JSON，不要 Markdown，不要解释。JSON 格式：
{
  "summary": "100字内总体概括",
  "topics": [
    {
      "topic": "话题名",
      "time_range": "HH:MM-HH:MM",
      "contributors": ["成员A", "成员B"],
      "detail": "谁提出了什么、讨论了什么、有什么结论",
      "evidence": ["原话摘录1", "原话摘录2"]
    }
  ],
  "user_titles": [
    {"name": "成员名", "title": "简短称号", "reason": "为什么给这个称号"}
  ]
}

要求：
- 话题必须按连续对话内容和语义聚合，不要按关键词机械拆分。
- 不要求固定数量；只保留真实形成讨论的主题，通常 3-8 个即可，少就少。
- 单句寒暄、单张图片、@某人、纯表情、无上下文短句不要单独列为话题。
- @对象不是话题，也不是有效证据；纯@消息必须忽略，除非后续有实质内容形成同一段讨论。
- 如果短句是同一段讨论的一部分，应合并到对应话题。
- contributors 必须来自聊天记录中出现的成员名。
- user_titles 只给真实有发言的人，称号要基于行为，不要攻击性。
- 不要把"我"误写成聊天记录里的其他联系人。
- evidence 使用短摘录，不超过 3 条，每条不超过 40 字。

聊天记录：
{messages_text}
```

## 输出校验

生成 JSON 后自检：

- 可被 `json.loads` 解析
- 含 `summary`、`topics`（数组）、`user_titles`（数组）
- `topics[].evidence` 每条 ≤ 40 字
- 保存到 `export/reports/analysis_{date}_{safe_group}.json`
