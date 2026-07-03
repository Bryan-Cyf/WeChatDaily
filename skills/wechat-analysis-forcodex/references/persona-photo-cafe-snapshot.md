# 真人画像预设：cafe-snapshot

先应用 `persona-photo-realism-rules.md`，再使用本模板。未指定场景时默认用本预设。

```text
Use case: photorealistic-natural
Asset type: fictional persona portrait for a WeChat chat-analysis report
Primary request: Create a realistic smartphone-photo style portrait of a fictional adult {gender_text} inspired by the chat persona "{name}". This is an imagined character based on chat temperament, not a likeness or real portrait of any person.

Persona cues: {persona_cues}
Age: {age_instruction}. If the user did not explicitly provide an age, use 18-25 years old young adult only; avoid mature, middle-aged, or older-looking features.

Scene/backdrop: casual cafe or office lounge in a Chinese city, window light, ordinary table, phone, laptop or drink nearby, background softly blurred but believable.
Subject styling: natural good-looking everyday outfit, clean but not over-styled, relaxed hair, light natural makeup if female, ordinary life texture.
Composition: vertical mobile phone snapshot, seated or leaning by a table, relaxed posture, subtle confident smile, looking slightly off-camera.
Lighting/mood: soft natural daylight, warm and real, not a commercial portrait.

Constraints: no text, no watermark, no logo, no WeChat UI, no ID badge, no real-person likeness, no celebrity likeness, no cartoon/anime style, no plastic skin, no template influencer face, no studio glamour.
```
