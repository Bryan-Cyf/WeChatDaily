# 真人随拍画像风格入口

用户要求根据聊天画像生成真人真实感、手机随拍、照片风格人物图时，先读本文件，再读取 `persona-photo-realism-rules.md` 和选中的单个预设模板。不要一次加载全部预设。

## 通用规则

- 所有真人画像都是“基于聊天气质的虚构真人感用户画像”，不是真人还原。
- 性别优先使用 `story_*.json` 或 `stats_*.json` 里的微信性别字段；`unknown` 时不要按名字猜。
- 年龄默认强约束：用户未明确指定年龄时，一律设为 18-25 岁年轻成人；用户明确指定年龄时才覆盖该默认值。
- 不要用“成年”“自然年龄段”“adult age”等宽泛年龄词替代默认年龄范围。
- 场景、穿搭只有用户明确指定时才强约束。
- 用户说“更真实”“像手机拍的”时，优先降低棚拍感：普通光线、生活背景、自然表情、真实皮肤纹理。
- 默认追求自然好看，不要故意增加明显瑕疵。

## 预设选择

| 风格 ID | 适合场景 | 读取文件 |
|---|---|---|
| `badminton-court` | 羽毛球场手机随拍，运动后清爽、有活力 | `persona-photo-badminton-court.md` |
| `cafe-snapshot` | 咖啡店/办公休息区随拍，温和聪明、生活化；默认通用 | `persona-photo-cafe-snapshot.md` |
| `city-commute` | 地铁口/街边通勤随拍，独立利落、有都市感 | `persona-photo-city-commute.md` |
| `desk-coder` | 电脑桌/工位随拍，适合技术浓度高、工具链话题多的人 | `persona-photo-desk-coder.md` |
| `night-market` | 夜市/饭局随拍，适合吃喝、吐槽、群聊气氛组 | `persona-photo-night-market.md` |
| `bookstore-weekend` | 书店/图书馆周末随拍，适合小说、短剧、学习、观察型人格 | `persona-photo-bookstore-weekend.md` |
| `home-gaming` | 居家电竞/游戏角随拍，适合游戏梗、开黑、吐槽玩家 | `persona-photo-home-gaming.md` |
| `outdoor-hiking` | 户外徒步/公园随拍，适合旅行、运动、行动派故事线 | `persona-photo-outdoor-hiking.md` |

## 默认选择

- 用户指定场景时严格使用对应预设。
- 用户未指定时，根据画像关键词选择；无法判断时用 `cafe-snapshot`。
- 生成后复制图片到 `reports\<safe_target>_<persona-style>.png`。
