# 磁性纪录片男声配音与智能混音 Skill (`documentary-voiceover-pipeline`)

一套专为中文中长视频（B站、YouTube、视频号深度科技/商业/历史纪录片）打造的**超拟真男声配音、时间轴字幕（`.srt`）生成与自适应情绪 BGM 侧链闪避混音**通用 Skill。

## 目录结构

```text
.
├── SKILL.md                                   # Antigravity Skill 核心指令文件
├── README.md                                  # 项目说明文档
├── .gitignore                                 # Git 忽略规则（防密钥与临时文件提交）
└── scripts/
    ├── generate_voiceover.py                  # 主力通用脚本（云健 zh-CN-YunjianNeural + 7种情绪BGM + 自动闪避混音 + SRT字幕）
    └── cloud_gemini_lyria_voiceover.sh        # 可选云端脚本（Google Gemini 3.8 Flash TTS + Lyria 3.5 配乐）
```

## 快速开始

### 1. 准备虚拟环境（首次运行）

```bash
python3 -m venv /tmp/voiceover_venv
/tmp/voiceover_venv/bin/pip install edge-tts numpy
```

### 2. 一键生成配音、字幕与自适应 BGM 混音

支持直接传入 Markdown 视频文案（`.md`）、纯文本（`.txt`）或结构化章节 JSON（`.json`）：

```bash
/tmp/voiceover_venv/bin/python3 ./scripts/generate_voiceover.py \
  --input "你的视频文案.md" \
  --output-dir "./音频产出" \
  --voice "zh-CN-YunjianNeural" \
  --rate "-4%" \
  --title "视频名称"
```

### 3. 仅生成纯人声配音与 SRT 字幕（不含背景音乐）

```bash
/tmp/voiceover_venv/bin/python3 ./scripts/generate_voiceover.py \
  --input "你的视频文案.md" \
  --output-dir "./音频产出" \
  --no-bgm
```

## 常用男声声线列表

- `zh-CN-YunjianNeural`（**云健，默认推荐**）：磁性沉稳纪录片男声，配合 `-4%` 语速与 160Hz 胸腔共鸣增益最具大片感。
- `zh-CN-YunxiNeural`（**云希**）：年轻阳光科技 UP 主男声。
- `zh-CN-YunyangNeural`（**云扬**）：专业沉稳新闻专题片播音男声。
