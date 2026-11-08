# -*- coding: utf-8 -*-
"""声纹录入：让桌宠只认主人的声音

用法：
    python voice-enroll.py            # 录 4 段，每段按提示说一句话
    python voice-enroll.py --check    # 只测：录一段，和已有声纹比对

录完会写 D:\\桌面\\dafeiyu\\dsh-pet-data\\voice-print.json
voice-chat.py 每次识别前会拿这句音频跟它比对，相似度不够就不理。
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import sounddevice as sd

SR = 16000
DATA = r"D:\桌面\dafeiyu\dsh-pet-data"
MODEL = os.path.join(DATA, "asr-models", "sv", "campplus.onnx")
PROFILE = os.path.join(DATA, "voice-print.json")

PROMPTS = [
    "我是这个电脑的主人，现在给桌宠录入声纹。",
    "今天过得还不错，想听你说说话。",
    "小鱼，你还记得我们昨天聊了什么吗？",
    "我说话的速度和语调，你以后要认得出来。",
]


def log(msg):
    print(time.strftime("%H:%M:%S") + "  " + msg, flush=True)


def load_ext():
    import sherpa_onnx
    cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=MODEL, num_threads=2)
    return sherpa_onnx.SpeakerEmbeddingExtractor(cfg)


def record(seconds=4.0, device=None):
    log("请开始说话（%.0f 秒）…" % seconds)
    a = sd.rec(int(seconds * SR), samplerate=SR, channels=1, dtype="float32", device=device)
    sd.wait()
    x = a.reshape(-1)
    rms = float(np.sqrt(np.mean(x ** 2)))
    log("录完，音量 rms=%.4f" % rms)
    return x


def embed(ext, x):
    s = ext.create_stream()
    s.accept_waveform(SR, x)
    s.input_finished()
    return np.array(ext.compute(s), dtype=np.float32)


def cos(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--device", type=int, default=None)
    args = ap.parse_args()

    if not os.path.exists(MODEL):
        log("找不到声纹模型：" + MODEL)
        return 1

    ext = load_ext()
    log("声纹模型已加载（维度 %d）" % ext.dim)

    if args.check:
        if not os.path.exists(PROFILE):
            log("还没有声纹档案，先跑一次录入")
            return 1
        prof = json.load(open(PROFILE, encoding="utf-8"))["embedding"]
        base = np.array(prof, dtype=np.float32)
        x = record(4.0, args.device)
        log("相似度：%.3f（阈值 %.2f）" % (cos(embed(ext, x), base), json.load(open(PROFILE, encoding="utf-8")).get("threshold", 0.45)))
        return 0

    embs = []
    for i, p in enumerate(PROMPTS, 1):
        log("第 %d/%d 段：%s" % (i, len(PROMPTS), p))
        input("准备好后按回车开始…")
        x = record(4.0, args.device)
        e = embed(ext, x)
        embs.append(e)
        if len(embs) >= 2:
            log("  与上一段相似度 %.3f" % cos(e, embs[-2]))

    mean = np.mean(np.stack(embs), axis=0)
    mean = mean / (np.linalg.norm(mean) + 1e-9)
    sims = [cos(e, mean) for e in embs]
    log("各段与平均值相似度：%s" % ", ".join("%.2f" % s for s in sims))
    profile = {
        "enabled": True,
        "threshold": 0.45,
        "min_sec": 1.2,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "embedding": [round(float(v), 6) for v in mean],
    }
    json.dump(profile, open(PROFILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("已保存：" + PROFILE)
    log("阈值 %.2f；voice-chat.py 重启后生效" % profile["threshold"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
