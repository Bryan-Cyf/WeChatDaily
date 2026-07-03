# 图片风格入口

先读取本文件选择风格，再只读取对应的单个风格文档。不要一次加载全部风格文档。

## 强制执行规则

- 用户点名风格、IP、游戏、媒介或关键词时，必须先查下面的“硬路由表”。硬路由命中时直接使用对应风格 ID，不要再按聊天气质重新选择。
- 命中风格 ID 后，必须读取“读取文件”列中的模板文件，并把模板里的 Required visible text、Section 标题、Composition、Palette、Constraints 合并进最终 `image_gen` 提示词。
- 不要只读本索引就直接生成图片；本索引只负责路由，具体画面必须来自被选中的模板文件。
- 如果用户要求的风格和真人随拍、故事线长图冲突，优先满足用户明确说出的产物类型：真人/照片走 `persona-photo`，故事线长图走 `story-handbook`，普通聊天总结海报再走创意风格。

## 通用规则

- 所有风格都必须使用 Codex 内置 `image_gen`，不走 HTML 渲染或截图。
- 所有风格都必须保留：话题区、群友角色卡、结论区。
- 人物/话题故事线长图读取 `story-handbook-prompt-template.md`。
- 真人随拍画像先读取 `persona-photo-style-index.md`，再读取 `persona-photo-realism-rules.md` 和选中的单个预设模板。
- 群友角色卡必须使用导出 JSON 的 `speaker_profiles[*].gender`：
  - `male`：男性化但不过度刻板的小像。
  - `female`：女性化但不过度刻板的小像。
  - `unknown`：中性小像。
- 性别不能按名字猜；微信读不到性别就使用中性形象。
- 不展示原始聊天截图，不输出手机号、密钥、二维码、链接 token。

## 风格选择

| 风格 ID | 适合场景 | 读取文件 |
|---|---|---|
| `avatar-daily` | 默认日报；用户喜欢参考图 1 的手账、毛笔字、角色卡风格 | `avatar-daily-prompt-template.md` |
| `starship-log` | 技术排障、工具链、Agent、模型讨论多 | `style-starship-log.md` |
| `card-compendium` | 想突出群友称号、角色属性和收藏卡感 | `style-card-compendium.md` |
| `radio-program` | 话题跨度大、吐槽和生活内容多 | `style-radio-program.md` |
| `convenience-shelf` | 更轻松、社交平台感、更像趣味小报 | `style-convenience-shelf.md` |
| `valorant-tactical` | 想做无畏契约/战术射击游戏主题，更有对局、技能、战报和梗图感 | `style-valorant-tactical.md` |
| `story-handbook` | 某个人、某个话题、八卦或事件链路的手帐长图 | `story-handbook-prompt-template.md` |
| `persona-photo` | 根据聊天画像生成真人随拍风虚构形象 | `persona-photo-style-index.md` |

## 硬路由表

| 用户说法命中 | 必选风格 ID | 必须读取 |
|---|---|---|
| `无畏契约`、`Valorant`、`VALORANT`、`瓦风`、`打瓦`、`瓦罗兰特`、`瓦罗兰`、`战术射击`、`FPS 对局`、`特工阵容`、`对局战报`、`赛后结算`、`拆包`、`架枪`、`技能 CD` | `valorant-tactical` | `style-valorant-tactical.md` |
| `飞船`、`星舰`、`舰长日志`、`太空舱`、`星际`、`故障排查`、`Agent 工具链` | `starship-log` | `style-starship-log.md` |
| `卡牌`、`收藏卡`、`图鉴`、`角色卡`、`群友称号`、`属性面板` | `card-compendium` | `style-card-compendium.md` |
| `电台`、`广播`、`脱口秀`、`节目单`、`主持人`、`场外连线` | `radio-program` | `style-radio-program.md` |
| `便利店`、`货架`、`小票`、`零食`、`轻松小报`、`朋友圈感` | `convenience-shelf` | `style-convenience-shelf.md` |
| `手账`、`日报`、`毛笔字`、`默认风格`、`参考图 1` | `avatar-daily` | `avatar-daily-prompt-template.md` |
| `故事线`、`事件链路`、`某个人的链路`、`话题链路`、`八卦长图` | `story-handbook` | `story-handbook-prompt-template.md` |
| `真人`、`真实照片`、`手机随拍`、`生活照`、`画出 TA 的样子`、`虚构真人感画像` | `persona-photo` | `persona-photo-style-index.md` |

## 默认选择

- 用户没有指定风格时，使用 `avatar-daily`。
- 用户说“新鲜”“创意”“换个风格”但未指定具体方向时：
  - 技术浓度高：选 `starship-log`。
  - 群友称号是重点：选 `card-compendium`。
  - 生活/吐槽/八卦跨度大：选 `radio-program`。
  - 想轻松好玩、适合发群里：选 `convenience-shelf`。
  - 想游戏化、有对局感、梗味更重：选 `valorant-tactical`。
- 用户要求“故事线”“某个人的链路”“话题链路”时，选 `story-handbook`。
- 用户要求“真人”“真实照片”“手机随拍”“画出 TA 的样子”时，选 `persona-photo`。

## 生成前自检

调用 `image_gen` 前，按选中的风格检查：

- 用户原话命中硬路由时，最终风格 ID 必须等于硬路由表里的 ID。
- 已读取对应模板文件；不能只根据本索引或模型常识生成。
- 最终提示词包含模板文件里的必需区块标题、视觉语言和约束。
- `valorant-tactical` 必须包含 `今日对局`、`特工阵容`、`赛后结算`、`无畏契约风战报` 或 `战术对局日报`，并包含特工选择、技能卡、比分板、小地图路线、拆包/守包目标中的多数元素。
- 如果自检不通过，先补读对应模板并重写提示词，再调用 `image_gen`。
