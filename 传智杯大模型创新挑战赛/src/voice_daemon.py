# -*- coding: utf-8 -*-
"""桌宠语音守护进程（重建版）

协议（与插件约定）：
  从 stdin 逐行读取"文本文件路径"
  文件内容是纯文本，或 JSON：{text, voice, speed, style, greeting, prewarm, silent}
  text 为空 = 预热，不播放

行为：
  ① Fish Audio 合成（读 fish-key.txt / voice.json 里的代理）
  ② 缓存到 voice-cache/[key].mp3（同文本同音色只合成一次）
  ③ 解码成 wav 用 winsound 播放（阻塞播放，保证顺序）
  ④ 追加记录到 corpus/speech.jsonl
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

import requests
import soundfile as sf
import numpy as np
import io
import winsound
import subprocess


BASE = r"D:\桌面\dafeiyu\dsh-pet-data"
CACHE = os.path.join(BASE, "voice-cache")
CORPUS = os.path.join(BASE, "corpus")
VOICE_JSON = os.path.join(BASE, "voice.json")
KEY_FILE = os.path.join(BASE, "fish-key.txt")
BGM_PS = os.path.join(BASE, "bgm.ps1")
CREATE_NO_WINDOW = 0x08000000


def log(msg):
    try:
        os.makedirs(CORPUS, exist_ok=True)
        with open(os.path.join(CORPUS, "daemon.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def read_cfg():
    try:
        raw = open(VOICE_JSON, encoding="utf-8-sig").read()
        raw = re.sub(r"(?m)^\s*//.*$", "", raw)
        cfg = json.loads(raw)
    except Exception:
        cfg = {}
    try:
        cfg["__key"] = open(KEY_FILE, encoding="utf-8-sig").read().strip()
    except Exception:
        cfg["__key"] = ""
    return cfg


def cache_key(text, voice, speed):
    h = hashlib.md5((voice + "|" + str(speed) + "|" + text).encode("utf-8")).hexdigest()
    return h


def synth_fish(text, voice, speed, cfg):
    key = cache_key(text, voice, speed)
    os.makedirs(CACHE, exist_ok=True)
    mp3 = os.path.join(CACHE, key + ".mp3")
    if os.path.exists(mp3) and os.path.getsize(mp3) > 800:
        return mp3, True
    payload = {
        "text": text,
        "reference_id": voice,
        "format": "mp3",
        "normalize": True,
        "latency": "low",
    }
    if speed and abs(float(speed) - 1.0) > 0.01:
        payload["prosody"] = {"speed": float(speed)}
    headers = {
        "Authorization": "Bearer " + cfg.get("__key", ""),
        "Content-Type": "application/json",
        "model": cfg.get("fishModel") or "s2.1-pro-free",
    }
    proxy = cfg.get("proxy")
    proxies = {"http": proxy, "https": proxy} if proxy else None
    for attempt in range(3):
        try:
            r = requests.post(cfg.get("fishApi") or "https://api.fish.audio/v1/tts",
                              json=payload, headers=headers, proxies=proxies, timeout=90)
            if r.status_code == 200 and len(r.content) > 800:
                open(mp3, "wb").write(r.content)
                return mp3, False
            log("合成失败 HTTP %s" % r.status_code)
        except Exception as e:
            log("合成异常 %s: %s" % (type(e).__name__, str(e)[:80]))
        time.sleep(1.5)
    return None, False


def play(mp3, gain_db=0.0):
    try:
        a, sr = sf.read(mp3, dtype="float32", always_2d=False)
    except Exception as e:
        log("解码失败: " + str(e)[:80])
        return False
    if a.ndim > 1:
        a = a.mean(axis=1)
    if gain_db:
        a = a * (10 ** (gain_db / 20.0))
    a = np.clip(a, -1.0, 1.0)
    pcm = (a * 32767).astype(np.int16).tobytes()
    # 拼一个最小 wav 头，直接内存播放
    import struct
    hdr = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16)
    hdr += b"data" + struct.pack("<I", len(pcm))
    try:
        winsound.PlaySound(hdr + pcm, winsound.SND_MEMORY)
        return True
    except Exception as e:
        log("播放失败: " + str(e)[:80])
        return False


def start_bgm(cfg, duration_ms):
    """说话时带弱化 BGM：另起一个播放器进程，和语音同时播，结束后淡出"""
    try:
        b = cfg.get("bgm") or {}
        if b.get("enabled") is False:
            log("BGM 未启用（enabled=false）")
            return None
        f = b.get("file") or ""
        if not f or not os.path.exists(f):
            log("BGM 文件不存在: " + str(f))
            return None
        if not os.path.exists(BGM_PS):
            log("BGM 脚本不存在: " + BGM_PS)
            return None
        args = [
            "powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
            "-File", BGM_PS,
            "-Clip", f,
            "-Start", str(float(b.get("start", 1))),
            "-Volume", str(float(b.get("ratio", 0.2))),
            "-FadeMs", str(int(b.get("fadeMs", 6000))),
            "-HoldMs", str(int(b.get("holdMs", 1200))),
            "-DurationMs", str(int(duration_ms)),
        ]
        proc = subprocess.Popen(args, creationflags=CREATE_NO_WINDOW,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("BGM 已启动 pid=" + str(proc.pid) + " 时长=" + str(duration_ms) + "ms 音量=" + str(b.get("ratio")))
        return proc
    except Exception as e:
        log("BGM 启动失败: " + str(e)[:80])
        return None


def record(entry):
    try:
        os.makedirs(CORPUS, exist_ok=True)
        with open(os.path.join(CORPUS, "speech.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def handle(line, cfg):
    path = line.strip().strip('"')
    if not path or not os.path.exists(path):
        return
    try:
        raw = open(path, encoding="utf-8-sig").read().strip()
    except Exception:
        return
    finally:
        try:
            os.remove(path)
        except Exception:
            pass
    if not raw:
        return
    opts = {}
    if raw.startswith("{"):
        try:
            opts = json.loads(raw)
        except Exception:
            opts = {"text": raw}
    else:
        opts = {"text": raw}

    text = str(opts.get("text") or "").strip()
    if text == "":
        return  # 预热
    voice = opts.get("voice") or cfg.get("fishVoice") or ""
    speed = float(opts.get("speed") or 1.0)
    gain = float(opts.get("gain") or 0.0)

    prewarm = bool(opts.get("prewarm"))
    mp3, hit = synth_fish(text, voice, speed, cfg)
    if not mp3:
        record({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "engine": "fish", "voice": voice,
                "text": text, "spoken": "", "error": "synth-failed", "hit": False})
        return
    if prewarm:
        # 只合成、不播放：等动画播完真正开口时命中缓存，几乎瞬时出声
        record({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "engine": "fish", "voice": voice,
                "greeting": bool(opts.get("greeting")), "text": text, "spoken": "", "hit": bool(hit),
                "prewarm": True, "played": False})
        return
    dur_ms = 0
    try:
        a, sr = sf.read(mp3, dtype="float32", always_2d=False)
        dur_ms = int(len(a) / sr * 1000)
    except Exception:
        dur_ms = 3000
    bgm_proc = None
    if opts.get("greeting"):
        b = cfg.get("bgm") or {}
        lead = int(b.get("leadMs", 800))
        tail = int(b.get("tailMs", 6000))
        # BGM 总时长 = 前奏 + 语音 + 尾奏（尾奏后再按 fadeMs 淡出）
        bgm_proc = start_bgm(cfg, lead + dur_ms + tail)
        if bgm_proc is not None and lead > 0:
            time.sleep(lead / 1000.0)
    ok = play(mp3, gain)
    if bgm_proc is not None:
        try:
            bgm_proc.wait(timeout=30)
        except Exception:
            try:
                bgm_proc.kill()
            except Exception:
                pass
    record({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "engine": "fish", "voice": voice,
            "greeting": bool(opts.get("greeting")), "style": opts.get("style") or "",
            "text": text, "spoken": text, "hit": bool(hit), "played": bool(ok)})


def main():
    cfg = read_cfg()
    log("语音守护启动 pid=%s" % os.getpid())
    for line in sys.stdin:
        try:
            handle(line, cfg)
        except Exception as e:
            log("处理异常: " + str(e)[:100])


if __name__ == "__main__":
    main()
