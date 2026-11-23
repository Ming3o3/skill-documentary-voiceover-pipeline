---
name: documentary-voiceover-pipeline
description: >-
  Use this skill whenever the user wants to generate human-like Chinese video
  voiceover (especially the magnetic documentary male voice 云健 Yunjian
  zh-CN-YunjianNeural, or tech UP主 voice 云希 Yunxi / news voice 云扬 Yunyang),
  synthesize chapter-matched background music (BGM), generate time-aligned SRT
  subtitles, or mix voiceover and BGM with FFmpeg sidechain auto-ducking (or
  cloud Google Gemini TTS & Lyria).
---

# 磁性纪录片男声配音与智能混音流水线 (`documentary-voiceover-pipeline`)

本 Skill 提供一套开箱即用的**中文长中短视频配音、字幕生成与背景音乐自动闪避混音（Auto-Ducking）**标准工作流。默认采用极具大片叙事质感的**超拟真神经网络男声：云健（`zh-CN-YunjianNeural`）**，配合从容自然的 `-4%` 舒缓语速、段落间 `0.65s` 呼吸气口以及广播级人声 EQ 温暖度增益，同时支持一键切换至 Google Gemini API 云端语音（`gemini-3.8-flash-tts`）与配乐（`lyria-3.5`）。

---

## 1. 核心声线与默认参数

| 声线代号 | 语音模型 ID (`edge-tts`) | 风格定位 | 推荐语速 (`--rate`) | 适用视频类型 |
| :--- | :--- | :--- | :--- | :--- |
| **云健（默认主力）** | `zh-CN-YunjianNeural` | **磁性沉稳纪录片男声**（胸腔共鸣饱满、叙事感强） | `-4%`（舒缓从容，不赶时间） | 科技商业复盘、历史人物传记、深度纪录片、硬核科普 |
| **云希（备选）** | `zh-CN-YunxiNeural` | **年轻阳光科技 UP 主男声**（亲切自然、互动感强） | `-2%` ~ `+0%` | 数码测评、编程教程、日常科技 Vlog |
| **云扬（备选）** | `zh-CN-YunyangNeural` | **权威沉稳新闻播音男声**（字正腔圆、央视专题片风） | `-4%` | 行业报告、政经解读、官方宣传片 |

### 广播级人声后期滤镜链（FFmpeg Vocal Chain）
为消除合成语音的单薄感，所有生成段落默认经过以下 FFmpeg 音频工程处理：
- **低切滤波**：`highpass=f=75`（滤除 75Hz 以下低频浑浊杂音）
- **胸腔磁性增益**：`equalizer=f=160:t=q:w=1.2:g=1.5`（提升 160Hz 男声胸腔温暖共鸣）
- **咬字清晰度提亮**：`equalizer=f=3200:t=q:w=1.2:g=1.5`（提升 3.2kHz 齿音与唇齿清晰度）
- **广播级动态压缩**：`acompressor=threshold=-18dB:ratio=2.2:attack=15:release=160`（平衡句首句尾音量动态）

---

## 2. 标准执行步骤（Agent 操作指南）

当用户提供一篇视频文案（Markdown 文档 `.md`、纯文本 `.txt` 或口播稿）并要求生成配音、字幕或背景音乐时，按以下步骤执行：

### 第一步：准备 Python 虚拟环境（规避 macOS PEP 668 限制）
如果本机尚未创建包含 `edge-tts` 与 `numpy` 的虚拟环境，先在 `/tmp/voiceover_venv`（或当前会话 `scratch/venv`）中初始化：

```bash
python3 -m venv /tmp/voiceover_venv
/tmp/voiceover_venv/bin/pip install -q edge-tts numpy
```

### 第二步：准备或解析视频文案
通用脚本 [generate_voiceover.py](./scripts/generate_voiceover.py) 支持三种输入格式：
1. **Markdown 视频文案 (`.md`)**：自动识别 `## 章节标题` 以及 `> 口播逐字稿` 引用块（或普通正文段落），自动过滤表格、代码块以及 `【BGM】`、`【画面/视觉】` 等分镜提示词。
2. **纯文本口播稿 (`.txt`)**：按空行或换行自动切分段落。
3. **结构化章节配置 (`.json`)**：可精确指定每个章节的 `id`、`title`、`style`（配乐情绪）和 `paragraphs` 列表。

> **口播文本预处理规范**：
> - 将容易被误读的符号转化为自然口语（例如 `$8 / $40` 写作 `8 美元输入、40 美元输出`，`~70%+` 写作 `超过百分之七十`）。
> - 在中英文专有名词衔接处保留空格（如 `Google DeepMind`、`Gemini 4 Neon`），确保神经网络连读自然。

### 第三步：运行通用配音与混音脚本
调用本 Skill 自带的 [generate_voiceover.py](./scripts/generate_voiceover.py) 一键产出纯配音、7 种情绪自适应立体声 BGM、侧链闪避混音成品以及毫秒级对齐的 `.srt` 字幕文件：

```bash
/tmp/voiceover_venv/bin/python3 "<SKILL_DIR>/scripts/generate_voiceover.py" \
  --input "你的视频文案.md" \
  --output-dir "./音频产出" \
  --voice "zh-CN-YunjianNeural" \
  --rate "-4%" \
  --title "视频项目名称"
```

常用可选参数：
- `--voice`: 默认为 `zh-CN-YunjianNeural`（云健），可换 `zh-CN-YunxiNeural`（云希）或 `zh-CN-YunyangNeural`（云扬）。
- `--rate`: 语速百分比，默认 `"-4%"`（自然舒缓纪录片节奏）；若需稍快可设 `"+0%"` 或 `"+5%"`，更慢可设 `"-8%"`。
- `--pause`: 段落之间的自然呼吸气口秒数，默认 `0.65`。
- `--no-bgm`: 仅生成纯人声配音与 `.srt` 字幕，不合成背景音乐。
- `--generate-samples`: 同时在 `00_三种男声试听对比/` 目录下生成云健、云希、云扬三款男声的开场试听对比 WAV。

### 第四步：验证输出产物并向用户交付
运行完成后，检查 `--output-dir` 下的产出文件，并使用 `file://` 可点击链接向用户汇报：
1. `<title>_配音+BGM混音成品_完整版.mp3`（经过 FFmpeg `sidechaincompress` 侧链闪避：有人说话时 BGM 自动压低，停顿留白处 BGM 自然浮现）
2. `<title>_纯配音_完整版.mp3`
3. `<title>_纯背景音乐_完整版.mp3`
4. `<title>_匹配时间轴字幕.srt`（可直接拖入剪映 / Premiere / Final Cut Pro）
5. `01_分段配音/`、`02_分段背景音乐/`、`03_分段混音预览/` 下的分章节高保真 `.wav` 文件与 `audio_manifest.json`。

---

## 3. 进阶：Google Gemini 3.8 Flash TTS + Lyria 3.5 云端双引擎模式

当用户配置了 `GEMINI_API_KEY` 且已安装 `gemini-api` CLI 插件时，可使用 `--engine gemini-cloud`（或配合 `gemini-api tts` 与 `gemini-api music`）调用谷歌云端模型：
- **云端语音**：`gemini-api tts -f chapter.txt -m gemini-3.8-flash-tts -v Kore --language zh-CN --out chapter_vo.wav`
- **云端配乐**：`gemini-api music "<英文配乐氛围描述>" -m lyria-3.5 --out bgm.wav`
- **自动闪避混音**：使用与本地完全一致的 FFmpeg `sidechaincompress` 滤镜链完成最终母带合成。
