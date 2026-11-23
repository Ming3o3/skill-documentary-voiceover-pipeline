#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用磁性纪录片男声（云健 Yunjian: zh-CN-YunjianNeural）配音、SRT字幕、自适应情绪BGM与侧链闪避混音工具
支持输入格式：
  1. Markdown 视频文案 (.md) —— 自动提取各章节下的 `> 口播逐字稿` 引用块（或正文段落）
  2. 纯文本口播稿 (.txt) —— 按空行或换行切分段落
  3. 结构化章节 JSON (.json) —— 包含 chapters: [{id, title, style, paragraphs}]
"""

import os
import re
import sys
import math
import wave
import json
import asyncio
import argparse
import subprocess
import numpy as np
import edge_tts

STYLE_CYCLES = [
    "suspense_to_epic",
    "retro_discovery",
    "tense_crisis",
    "breakthrough_rise",
    "high_energy_tech",
    "cyberpunk_showdown",
    "warm_interstellar_outro",
]


def infer_style_from_title(title, idx, total):
    """根据章节标题关键词或位置自动匹配最贴合的配乐情绪"""
    t = title.lower()
    if idx == 0 or any(k in t for k in ["开场", "引言", "序幕", "intro"]):
        return "suspense_to_epic"
    if idx == total - 1 or any(k in t for k in ["终局", "总结", "尾声", "思考", "未来", "结语", "outro"]):
        return "warm_interstellar_outro"
    if any(k in t for k in ["危机", "至暗", "警报", "暴跌", "翻车", "困境", "挑战"]):
        return "tense_crisis"
    if any(k in t for k in ["对决", "对比", "横评", "诸神", "跑分", "pk", "vs"]):
        return "cyberpunk_showdown"
    if any(k in t for k in ["爆发", "狂飙", "全面", "统治", "碾压", "高燃"]):
        return "high_energy_tech"
    if any(k in t for k in ["破局", "反击", "崛起", "突破", "逆转", "重磅"]):
        return "breakthrough_rise"
    if any(k in t for k in ["起源", "奠基", "历史", "早期", "诞生", "起点"]):
        return "retro_discovery"
    return STYLE_CYCLES[idx % len(STYLE_CYCLES)]


def clean_spoken_text(line):
    """清理 Markdown 格式符号，并将特殊符号转换为适合中文语音朗读的口语"""
    s = line.strip()
    s = re.sub(r"^>\s*", "", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    s = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", s)
    s = re.sub(r"^[-*•]\s+", "", s)
    return s.strip()


def parse_input_script(input_path):
    """解析 .md / .txt / .json 输入文案为统一章节结构"""
    ext = os.path.splitext(input_path)[1].lower()
    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    if ext == ".json":
        data = json.loads(content)
        chapters = data["chapters"] if isinstance(data, dict) and "chapters" in data else data
        for i, ch in enumerate(chapters):
            ch.setdefault("id", f"{i:02d}_章节")
            ch.setdefault("title", ch["id"])
            ch.setdefault("style", infer_style_from_title(ch["title"], i, len(chapters)))
            ch.setdefault("intro_pad", 2.0 if i == 0 else 1.5)
            ch.setdefault("outro_pad", 3.5 if i == len(chapters) - 1 else 2.5)
        return chapters

    if ext == ".md":
        lines = content.splitlines()
        raw_sections = []
        cur_title = "00_开场"
        cur_quotes = []
        cur_plain = []
        in_code_block = False

        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue

            m_h2 = re.match(r"^##\s+(.+)$", line.strip())
            if m_h2:
                if cur_quotes or cur_plain:
                    raw_sections.append((cur_title, cur_quotes if cur_quotes else cur_plain))
                cur_title = m_h2.group(1).strip()
                cur_quotes = []
                cur_plain = []
                continue

            # 跳过冗余小标题、表格、制作说明或分镜提示
            if any(k in cur_title for k in ["概览", "Timeline", "制作说明", "锦囊", "Production Notes"]):
                continue
            stripped = line.strip()
            if not stripped or stripped.startswith("|") or stripped.startswith("---") or stripped.startswith("###"):
                continue
            if any(stripped.startswith(p) for p in ["- **【BGM】**", "- **【画面", "**【口播", "- `0"]):
                continue

            if stripped.startswith(">"):
                cleaned = clean_spoken_text(stripped)
                if cleaned and not any(cleaned.startswith(k) for k in ["视频制作说明", "- 预计时长", "- 时间基准", "- 视频风格", "- 排版结构"]):
                    cur_quotes.append(cleaned)
            else:
                cleaned = clean_spoken_text(stripped)
                if cleaned and len(cleaned) > 8:
                    cur_plain.append(cleaned)

        if cur_quotes or cur_plain:
            raw_sections.append((cur_title, cur_quotes if cur_quotes else cur_plain))

        # 过滤只保留含有效口播段落的章节
        valid_sections = [(t, p) for t, p in raw_sections if p]
        chapters = []
        for idx, (title, paras) in enumerate(valid_sections):
            short_name = re.sub(r"[^\w\u4e00-\u9fa5]+", "_", title).strip("_")[:18]
            cid = f"{idx:02d}_{short_name}" if not re.match(r"^\d{2}_", short_name) else short_name
            chapters.append({
                "id": cid,
                "title": title,
                "style": infer_style_from_title(title, idx, len(valid_sections)),
                "intro_pad": 2.0 if idx == 0 else 1.5,
                "outro_pad": 4.0 if idx == len(valid_sections) - 1 else 2.5,
                "paragraphs": paras,
            })
        if chapters:
            return chapters

    # 默认按纯文本 (.txt) 处理
    paras = [clean_spoken_text(p) for p in re.split(r"\n\s*\n|\n", content) if clean_spoken_text(p)]
    return [{
        "id": "00_完整口播",
        "title": "00. 完整口播",
        "style": "suspense_to_epic",
        "intro_pad": 2.0,
        "outro_pad": 3.5,
        "paragraphs": paras,
    }]


def get_audio_duration(path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    return float(subprocess.check_output(cmd, text=True).strip())


def generate_silence_wav(path, duration_sec, sr=44100):
    n_samples = int(duration_sec * sr)
    silent = np.zeros((n_samples, 2), dtype=np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(silent.tobytes())


async def tts_paragraph_to_wav(sem, text, voice, rate, out_wav):
    tmp_mp3 = out_wav + ".tmp.mp3"
    async with sem:
        for attempt in range(4):
            try:
                communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
                await communicate.save(tmp_mp3)
                break
            except Exception as e:
                if attempt == 3:
                    raise e
                await asyncio.sleep(1.0 * (attempt + 1))

    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", tmp_mp3,
        "-af", "highpass=f=75,equalizer=f=160:t=q:w=1.2:g=1.5,equalizer=f=3200:t=q:w=1.2:g=1.5,acompressor=threshold=-18dB:ratio=2.2:attack=15:release=160",
        "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", out_wav
    ], check=True)
    if os.path.exists(tmp_mp3):
        os.remove(tmp_mp3)


async def generate_all_chapters_voiceover(chapters, vo_dir, sample_dir, voice, rate, pause_dur, generate_samples):
    sem = asyncio.Semaphore(5)
    temp_root = os.path.join(vo_dir, "_tmp_edge")
    os.makedirs(temp_root, exist_ok=True)

    tasks = []
    para_wav_map = {}
    for ch in chapters:
        cid = ch["id"]
        ch_tmp = os.path.join(temp_root, cid)
        os.makedirs(ch_tmp, exist_ok=True)
        for idx, para in enumerate(ch["paragraphs"]):
            wav_path = os.path.join(ch_tmp, f"p_{idx:02d}.wav")
            para_wav_map[(cid, idx)] = wav_path
            tasks.append(tts_paragraph_to_wav(sem, para, voice, rate, wav_path))

    if generate_samples and chapters and chapters[0]["paragraphs"]:
        os.makedirs(sample_dir, exist_ok=True)
        sample_text = " ".join(chapters[0]["paragraphs"][:2])
        tasks.append(tts_paragraph_to_wav(
            sem, sample_text, "zh-CN-YunjianNeural", rate,
            os.path.join(sample_dir, "试听1_云健_磁性纪录片男声.wav")
        ))
        tasks.append(tts_paragraph_to_wav(
            sem, sample_text, "zh-CN-YunxiNeural", rate,
            os.path.join(sample_dir, "试听2_云希_年轻科技UP主男声.wav")
        ))
        tasks.append(tts_paragraph_to_wav(
            sem, sample_text, "zh-CN-YunyangNeural", rate,
            os.path.join(sample_dir, "试听3_云扬_沉稳新闻播音男声.wav")
        ))

    await asyncio.gather(*tasks)

    results = []
    pause_wav = os.path.join(temp_root, "pause.wav")
    generate_silence_wav(pause_wav, pause_dur)

    for ch in chapters:
        cid = ch["id"]
        ch_tmp = os.path.join(temp_root, cid)
        seg_files = []
        para_timings = []
        cur_offset = ch["intro_pad"]

        intro_wav = os.path.join(ch_tmp, "intro_pad.wav")
        generate_silence_wav(intro_wav, ch["intro_pad"])
        seg_files.append(intro_wav)

        for idx, para in enumerate(ch["paragraphs"]):
            wav_path = para_wav_map[(cid, idx)]
            dur = get_audio_duration(wav_path)
            para_timings.append({
                "text": para,
                "start": cur_offset,
                "end": cur_offset + dur
            })
            seg_files.append(wav_path)
            cur_offset += dur
            if idx < len(ch["paragraphs"]) - 1:
                seg_files.append(pause_wav)
                cur_offset += pause_dur

        outro_wav = os.path.join(ch_tmp, "outro_pad.wav")
        generate_silence_wav(outro_wav, ch["outro_pad"])
        seg_files.append(outro_wav)
        cur_offset += ch["outro_pad"]

        concat_list_path = os.path.join(ch_tmp, "concat.txt")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for sf in seg_files:
                f.write(f"file '{sf}'\n")

        chapter_vo_wav = os.path.join(vo_dir, f"{cid}_配音.wav")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", concat_list_path, "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
            chapter_vo_wav
        ], check=True)

        actual_dur = get_audio_duration(chapter_vo_wav)
        results.append((ch, chapter_vo_wav, actual_dur, para_timings))

    subprocess.run(["rm", "-rf", temp_root], check=True)
    return results


def midi_to_freq(midi_note):
    return 440.0 * (2.0 ** ((midi_note - 69.0) / 12.0))


def soft_pad_wave(t, freq, harmonics=(1.0, 0.45, 0.2, 0.08), detune=0.0025):
    left = np.zeros_like(t)
    right = np.zeros_like(t)
    for idx, amp in enumerate(harmonics, start=1):
        f_l = freq * idx * (1.0 - detune * (idx % 2))
        f_r = freq * idx * (1.0 + detune * (idx % 2))
        left += amp * np.sin(2.0 * np.pi * f_l * t + idx * 0.3)
        right += amp * np.sin(2.0 * np.pi * f_r * t + idx * 0.7)
    norm = sum(harmonics)
    return left / norm, right / norm


def synthesize_chapter_bgm(chapter, bgm_dir, duration_sec, sr=44100):
    cid = chapter["id"]
    style = chapter.get("style", "suspense_to_epic")
    n_samples = int(math.ceil(duration_sec * sr))
    t = np.linspace(0.0, duration_sec, n_samples, endpoint=False)

    left = np.zeros(n_samples, dtype=np.float64)
    right = np.zeros(n_samples, dtype=np.float64)

    style_configs = {
        "suspense_to_epic": {
            "bpm": 100,
            "chords": [(50, 57, 62, 65), (46, 53, 58, 62), (41, 48, 53, 57), (48, 55, 60, 64)],
            "arp_notes": [62, 65, 69, 74, 72, 69, 65, 62],
            "bass_pulse_hz": 2.0,
            "brightness": 0.65
        },
        "retro_discovery": {
            "bpm": 96,
            "chords": [(45, 52, 57, 60), (41, 48, 53, 57), (48, 55, 60, 64), (43, 50, 55, 59)],
            "arp_notes": [60, 64, 67, 69, 72, 69, 67, 64],
            "bass_pulse_hz": 1.6,
            "brightness": 0.55
        },
        "tense_crisis": {
            "bpm": 116,
            "chords": [(40, 47, 52, 55), (48, 55, 59, 64), (45, 52, 57, 60), (47, 54, 59, 63)],
            "arp_notes": [64, 67, 71, 64, 63, 66, 71, 63],
            "bass_pulse_hz": 3.8,
            "brightness": 0.75
        },
        "breakthrough_rise": {
            "bpm": 108,
            "chords": [(41, 48, 53, 57), (43, 50, 55, 59), (45, 52, 57, 60), (48, 55, 60, 64)],
            "arp_notes": [65, 69, 72, 77, 76, 72, 69, 67],
            "bass_pulse_hz": 2.2,
            "brightness": 0.70
        },
        "high_energy_tech": {
            "bpm": 124,
            "chords": [(43, 50, 55, 58), (39, 46, 51, 55), (46, 53, 58, 62), (41, 48, 53, 57)],
            "arp_notes": [67, 70, 74, 79, 77, 74, 70, 67],
            "bass_pulse_hz": 4.0,
            "brightness": 0.85
        },
        "cyberpunk_showdown": {
            "bpm": 118,
            "chords": [(36, 43, 48, 51), (44, 51, 56, 60), (41, 48, 53, 56), (43, 50, 55, 59)],
            "arp_notes": [60, 63, 67, 72, 75, 72, 67, 63],
            "bass_pulse_hz": 3.5,
            "brightness": 0.80
        },
        "warm_interstellar_outro": {
            "bpm": 84,
            "chords": [(41, 48, 53, 57, 60), (40, 48, 55, 60), (38, 45, 53, 57), (43, 50, 55, 60)],
            "arp_notes": [60, 64, 67, 72, 76, 72, 67, 64],
            "bass_pulse_hz": 1.0,
            "brightness": 0.50
        }
    }

    cfg = style_configs.get(style, style_configs["suspense_to_epic"])
    bpm = cfg["bpm"]
    bar_sec = (60.0 / bpm) * 4.0
    chords = cfg["chords"]

    n_bars = int(math.ceil(duration_sec / bar_sec))
    for bar_idx in range(n_bars):
        start_s = int(bar_idx * bar_sec * sr)
        end_s = min(n_samples, int((bar_idx + 1) * bar_sec * sr))
        if end_s <= start_s:
            continue
        seg_t = t[start_s:end_s] - t[start_s]
        seg_len = end_s - start_s

        env = np.ones(seg_len, dtype=np.float64)
        fade_n = min(int(0.35 * sr), seg_len // 3)
        if fade_n > 0:
            env[:fade_n] = np.linspace(0.0, 1.0, fade_n)
            env[-fade_n:] = np.linspace(1.0, 0.0, fade_n)

        chord = chords[bar_idx % len(chords)]
        root_freq = midi_to_freq(chord[0])
        pulse_mod = 0.72 + 0.28 * np.sin(2.0 * np.pi * cfg["bass_pulse_hz"] * seg_t)
        sub_bass = 0.28 * np.sin(2.0 * np.pi * root_freq * seg_t) * pulse_mod * env

        pad_l = np.zeros(seg_len, dtype=np.float64)
        pad_r = np.zeros(seg_len, dtype=np.float64)
        for note in chord[1:]:
            nl, nr = soft_pad_wave(seg_t, midi_to_freq(note))
            pad_l += nl
            pad_r += nr
        pad_l = (pad_l / len(chord[1:])) * 0.34 * env
        pad_r = (pad_r / len(chord[1:])) * 0.34 * env

        left[start_s:end_s] += sub_bass + pad_l
        right[start_s:end_s] += sub_bass + pad_r

    step_sec = (60.0 / bpm) / 2.0
    arp_notes = cfg["arp_notes"]
    n_steps = int(duration_sec / step_sec)
    for s_idx in range(n_steps):
        if style == "suspense_to_epic" and (s_idx * step_sec) < 22.0 and (s_idx % 2 == 1):
            continue
        start_s = int(s_idx * step_sec * sr)
        note_dur = min(step_sec * 1.4, duration_sec - s_idx * step_sec)
        end_s = min(n_samples, start_s + int(note_dur * sr))
        if end_s <= start_s:
            continue
        nt = t[start_s:end_s] - t[start_s]
        note_midi = arp_notes[s_idx % len(arp_notes)]
        freq = midi_to_freq(note_midi)

        pluck_env = np.exp(-3.8 * nt / max(note_dur, 0.1))
        attack_n = min(int(0.012 * sr), len(nt) // 4)
        if attack_n > 0:
            pluck_env[:attack_n] *= np.linspace(0.0, 1.0, attack_n)

        sig = (
            0.75 * np.sin(2.0 * np.pi * freq * nt)
            + 0.25 * cfg["brightness"] * np.sin(2.0 * np.pi * (freq * 2.0) * nt)
        ) * pluck_env * 0.11

        pan = 0.3 + 0.4 * ((s_idx % 4) / 3.0)
        left[start_s:end_s] += sig * (1.0 - pan)
        right[start_s:end_s] += sig * pan

    if style == "tense_crisis":
        tick_interval = 60.0 / bpm
        for tk in range(int(duration_sec / tick_interval)):
            st = int(tk * tick_interval * sr)
            ed = min(n_samples, st + int(0.045 * sr))
            if ed > st:
                tt = t[st:ed] - t[st]
                tick = 0.08 * np.sin(2.0 * np.pi * 1850.0 * tt) * np.exp(-65.0 * tt)
                left[st:ed] += tick * (0.7 if tk % 2 == 0 else 0.3)
                right[st:ed] += tick * (0.3 if tk % 2 == 0 else 0.7)

    global_fade_in = min(int(1.8 * sr), n_samples // 6)
    global_fade_out = min(int(2.8 * sr), n_samples // 6)
    if global_fade_in > 0:
        fi = np.linspace(0.0, 1.0, global_fade_in)
        left[:global_fade_in] *= fi
        right[:global_fade_in] *= fi
    if global_fade_out > 0:
        fo = np.linspace(1.0, 0.0, global_fade_out)
        left[-global_fade_out:] *= fo
        right[-global_fade_out:] *= fo

    peak = max(np.max(np.abs(left)), np.max(np.abs(right)), 1e-6)
    stereo = np.stack([left / peak * 0.75, right / peak * 0.75], axis=1)
    pcm = (stereo * 32767.0).astype(np.int16)

    raw_bgm_wav = os.path.join(bgm_dir, f"_{cid}_raw.wav")
    final_bgm_wav = os.path.join(bgm_dir, f"{cid}_BGM.wav")
    with wave.open(raw_bgm_wav, "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())

    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", raw_bgm_wav,
        "-af", "lowpass=f=4800,aecho=0.8:0.88:65|110:0.25|0.18",
        "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", final_bgm_wav
    ], check=True)
    os.remove(raw_bgm_wav)
    return final_bgm_wav


def mix_vo_and_bgm(vo_wav, bgm_wav, out_wav):
    filter_complex = (
        "[0:a]volume=1.18,asplit=2[vo_main][vo_sc];"
        "[1:a]volume=0.36[bgm_pre];"
        "[bgm_pre][vo_sc]sidechaincompress=threshold=0.022:ratio=5:attack=25:release=480:makeup=1.0[bgm_ducked];"
        "[vo_main][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2,alimiter=limit=0.95[out]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-i", vo_wav, "-i", bgm_wav,
        "-filter_complex", filter_complex,
        "-map", "[out]", "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
        out_wav
    ], check=True)


def format_srt_time(seconds):
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:
        ms = 999
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def split_paragraph_into_srt_chunks(para_text, start_sec, end_sec):
    raw_parts = re.split(r"([。！？；，、：——])", para_text)
    clauses = []
    buf = ""
    for part in raw_parts:
        if not part:
            continue
        if re.match(r"[。！？；，、：——]", part):
            buf += part
            if len(buf) >= 10 or part in "。！？；":
                clauses.append(buf.strip())
                buf = ""
        else:
            buf += part
    if buf.strip():
        clauses.append(buf.strip())

    total_chars = sum(max(len(c), 1) for c in clauses)
    total_dur = max(end_sec - start_sec, 0.2)
    cur = start_sec
    entries = []
    for c in clauses:
        frac = max(len(c), 1) / total_chars
        c_dur = total_dur * frac
        clean_c = c.rstrip("，。、；：")
        entries.append((cur, cur + c_dur, clean_c))
        cur += c_dur
    return entries


async def run_pipeline(args):
    out_dir = os.path.abspath(args.output_dir)
    vo_dir = os.path.join(out_dir, "01_分段配音")
    bgm_dir = os.path.join(out_dir, "02_分段背景音乐")
    mix_dir = os.path.join(out_dir, "03_分段混音预览")
    sample_dir = os.path.join(out_dir, "00_三种男声试听对比")

    os.makedirs(vo_dir, exist_ok=True)
    if not args.no_bgm:
        os.makedirs(bgm_dir, exist_ok=True)
        os.makedirs(mix_dir, exist_ok=True)

    chapters = parse_input_script(args.input)
    print(f"📖 已解析输入文案 [{args.input}]，共 {len(chapters)} 个章节。")
    print(f"🎙️ 正在调用 [{args.voice}, 语速 {args.rate}] 并发生成神经网络人声配音...")

    chapter_vo_results = await generate_all_chapters_voiceover(
        chapters, vo_dir, sample_dir, args.voice, args.rate, args.pause, args.generate_samples
    )

    vo_files, bgm_files, mix_files = [], [], []
    srt_entries = []
    chapter_report = []
    global_time_offset = 0.0

    for ch, vo_wav, ch_dur, para_timings in chapter_vo_results:
        cid = ch["id"]
        vo_files.append(vo_wav)

        bgm_wav = None
        mix_wav = None
        if not args.no_bgm:
            print(f"  -> 正在为章节 [{ch['title']}] ({ch_dur:.1f}s) 合成 [{ch['style']}] 情绪 BGM 并进行侧链闪避混音...")
            bgm_wav = synthesize_chapter_bgm(ch, bgm_dir, ch_dur)
            mix_wav = os.path.join(mix_dir, f"{cid}_混音完成.wav")
            mix_vo_and_bgm(vo_wav, bgm_wav, mix_wav)
            bgm_files.append(bgm_wav)
            mix_files.append(mix_wav)

        for pt in para_timings:
            abs_start = global_time_offset + pt["start"]
            abs_end = global_time_offset + pt["end"]
            srt_entries.extend(split_paragraph_into_srt_chunks(pt["text"], abs_start, abs_end))

        chapter_report.append({
            "id": cid,
            "title": ch["title"],
            "style": ch.get("style"),
            "start_time": format_srt_time(global_time_offset).split(",")[0],
            "end_time": format_srt_time(global_time_offset + ch_dur).split(",")[0],
            "duration_sec": round(ch_dur, 2),
            "vo_path": os.path.relpath(vo_wav, out_dir),
            "bgm_path": os.path.relpath(bgm_wav, out_dir) if bgm_wav else None,
            "mix_path": os.path.relpath(mix_wav, out_dir) if mix_wav else None,
        })
        global_time_offset += ch_dur

    title_prefix = args.title or os.path.splitext(os.path.basename(args.input))[0]
    srt_path = os.path.join(out_dir, f"{title_prefix}_匹配时间轴字幕.srt")
    with open(srt_path, "w", encoding="utf-8") as sf:
        for idx, (st, ed, txt) in enumerate(srt_entries, start=1):
            sf.write(f"{idx}\n{format_srt_time(st)} --> {format_srt_time(ed)}\n{txt}\n\n")

    def concat_to_mp3(wav_list, out_mp3):
        list_txt = os.path.join(out_dir, "_concat_tmp.txt")
        with open(list_txt, "w", encoding="utf-8") as f:
            for w in wav_list:
                f.write(f"file '{w}'\n")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", list_txt, "-c:a", "libmp3lame", "-b:a", "192k", out_mp3
        ], check=True)
        os.remove(list_txt)

    full_vo_mp3 = os.path.join(out_dir, f"{title_prefix}_纯配音_完整版.mp3")
    concat_to_mp3(vo_files, full_vo_mp3)

    full_bgm_mp3 = None
    full_mix_mp3 = None
    if not args.no_bgm:
        full_bgm_mp3 = os.path.join(out_dir, f"{title_prefix}_纯背景音乐_完整版.mp3")
        full_mix_mp3 = os.path.join(out_dir, f"{title_prefix}_配音+BGM混音成品_完整版.mp3")
        concat_to_mp3(bgm_files, full_bgm_mp3)
        concat_to_mp3(mix_files, full_mix_mp3)

    total_min = int(global_time_offset // 60)
    total_sec = int(round(global_time_offset % 60))
    print(f"✅ 完成！总时长: {total_min:02d}:{total_sec:02d} ({global_time_offset:.1f}s)")

    manifest_path = os.path.join(out_dir, "audio_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as rf:
        json.dump({
            "voice": args.voice,
            "rate": args.rate,
            "total_duration_sec": round(global_time_offset, 2),
            "total_duration_formatted": f"{total_min:02d}:{total_sec:02d}",
            "full_mix_mp3": os.path.relpath(full_mix_mp3, out_dir) if full_mix_mp3 else None,
            "full_vo_mp3": os.path.relpath(full_vo_mp3, out_dir),
            "full_bgm_mp3": os.path.relpath(full_bgm_mp3, out_dir) if full_bgm_mp3 else None,
            "srt_path": os.path.relpath(srt_path, out_dir),
            "chapters": chapter_report,
        }, rf, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="磁性纪录片男声 (云健 Yunjian) 配音、字幕与 BGM 混音流水线")
    parser.add_argument("-i", "--input", required=True, help="输入文案路径 (.md / .txt / .json)")
    parser.add_argument("-o", "--output-dir", default="./音频产出", help="输出目录路径")
    parser.add_argument("-v", "--voice", default="zh-CN-YunjianNeural", help="Edge-TTS 语音 ID (默认: zh-CN-YunjianNeural 云健)")
    parser.add_argument("-r", "--rate", default="-4%", help="语速调整百分比 (默认: -4% 舒缓纪录片节奏)")
    parser.add_argument("-p", "--pause", type=float, default=0.65, help="段落间自然停顿秒数 (默认: 0.65)")
    parser.add_argument("-t", "--title", default="", help="输出文件名前缀")
    parser.add_argument("--no-bgm", action="store_true", help="仅生成纯配音与 SRT 字幕，不生成背景音乐")
    parser.add_argument("--generate-samples", action="store_true", help="同时生成云健、云希、云扬三款男声试听样音")
    args = parser.parse_args()
    asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    main()
