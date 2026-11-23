#!/usr/bin/env bash
# ==============================================================================
# Google Gemini 3.8 Flash TTS + Lyria 3.5 云端双引擎配音与配乐混音脚本
# 使用方法：
#   export GEMINI_API_KEY="你的API_KEY"
#   bash ./scripts/cloud_gemini_lyria_voiceover.sh -i "你的视频文案.txt" -o "./音频产出_云端版"
# ==============================================================================
set -euo pipefail

INPUT_FILE="${1:-}"
OUT_DIR="${2:-./音频产出_Gemini云端版}"

if [[ -z "$INPUT_FILE" || ! -f "$INPUT_FILE" ]]; then
  echo "用法: bash $0 <输入文案.txt/.md> [输出目录]"
  exit 1
fi

mkdir -p "$OUT_DIR"

if ! command -v gemini-api >/dev/null 2>&1; then
  echo "正在安装 gemini-api CLI..."
  curl -fsSL https://raw.githubusercontent.com/google-gemini/gemini-api-cli/main/scripts/install.sh | bash
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "1/3 正在调用 Google Lyria 3.5 (lyria-3.5) 生成科技纪录片背景音乐..."
gemini-api music "Cinematic technology documentary soundtrack, starting with deep suspenseful electronic pulse, evolving into warm retro analog synth arpeggios and triumphant futuristic orchestral synth pads, no vocals, high production value" \
  -m lyria-3.5 --out "$OUT_DIR/lyria_tech_bgm.wav"

echo "2/3 正在调用 Gemini 3.8 Flash TTS (gemini-3.8-flash-tts) 生成中文旁白配音..."
gemini-api tts -f "$INPUT_FILE" \
  -m gemini-3.8-flash-tts -v Kore --language zh-CN \
  --out "$OUT_DIR/gemini_voiceover.wav"

echo "3/3 正在使用 FFmpeg 侧链闪避 (Auto-Ducking) 将配音与 BGM 适配混音..."
ffmpeg -y -v error \
  -i "$OUT_DIR/gemini_voiceover.wav" \
  -stream_loop -1 -i "$OUT_DIR/lyria_tech_bgm.wav" \
  -filter_complex "[0:a]volume=1.18,asplit=2[vo_main][vo_sc];[1:a]volume=0.35[bgm_pre];[bgm_pre][vo_sc]sidechaincompress=threshold=0.022:ratio=5:attack=25:release=480[bgm_ducked];[vo_main][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2,alimiter=limit=0.95[out]" \
  -map "[out]" -c:a libmp3lame -b:a 192k "$OUT_DIR/配音+BGM混音成品_Gemini云端版.mp3"

echo "🎉 完成！成品位于: $OUT_DIR/配音+BGM混音成品_Gemini云端版.mp3"
