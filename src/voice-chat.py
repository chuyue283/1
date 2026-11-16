"""桌宠语音对话（常驻）

用法：
    python voice-chat.py                # 启动，F9 监听开关，F10 退出
    python voice-chat.py --send-test 你好   # 只测"发消息给桌宠"
    python voice-chat.py --auto-arm      # 启动即监听（自测用）

为什么不用音量判断：
    实测环境噪音峰值 0.066 比说话还大，纯音量阈值会一直误触发。
    改用 Silero VAD（faster-whisper 自带），它按"是不是人声"判断。

工作方式：
    录音 → 每 3 秒切一段 → VAD 判断有没有人声 → 有才送去 Whisper
    → 没在对话中：找唤醒词（小鱼/小女仆/蓝毛小女仆）
    → 唤醒后：直接发给桌宠，等它说完再继续听
"""
import argparse
import csv
import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request

_RUNTIME_SITE = os.path.join(
    os.path.expanduser("~"), ".dsh", "dsh-runtimes",
    "dsh-primary-runtime", "dependencies", "python", "Lib", "site-packages",
)
if os.path.isdir(_RUNTIME_SITE):
    sys.path.insert(0, _RUNTIME_SITE)

import numpy as np
import sounddevice as sd

SR = 16000
BLOCK = 480                 # 30ms
WINDOW_SEC = 3.0            # 每 3 秒切一段送 VAD
MIN_SPEECH_SEC = 0.6        # 这一段里至少要有 0.6 秒人声才识别
CHAT_IDLE_TIMEOUT = 45

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "voice-chat.log")
VOICE_DIR = os.path.join(os.environ.get("USERPROFILE", ""), ".dsh", "dsh-pet", "voice", "corpus")
SPEECH = os.path.join(VOICE_DIR, "speech.jsonl")
PORT_FILE = os.path.join(VOICE_DIR, "host-port.txt")

WAKE_WORDS = ["小鱼", "小女仆", "蓝毛小女仆"]
PROMPT = "小鱼，小女仆。"
# Whisper 有时吐繁体（魚/僕/藍），唤醒词匹配前先归一
T2S = str.maketrans({"魚": "鱼", "僕": "仆", "藍": "蓝", "貓": "猫", "麼": "么", "幹": "干"})
HOMOPHONE = [(["小于", "小五", "小语", "小余", "小玉", "小羽", "小宇", "小渝", "小鱼儿"], "小鱼")]


# ===================== 流式识别（边说边出字，给气泡看） =====================
ASR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(os.path.abspath(__file__)))), "asr-models", "paraformer")
_stream_rec = None
_stream = None
_draft_last = None
_draft_at = 0.0
_stream_q = queue.Queue(maxsize=200)
_stream_last_progress = 0.0
_draft_buf = []
_draft_owner = None
_draft_checked_at = 0.0


def init_stream_asr():
    """加载 sherpa-onnx 流式 paraformer（中文）。失败不影响主流程。"""
    global _stream_rec
    try:
        import sherpa_onnx
        t0 = time.time()
        _stream_rec = sherpa_onnx.OnlineRecognizer.from_paraformer(
            tokens=os.path.join(ASR_DIR, "tokens.txt"),
            encoder=os.path.join(ASR_DIR, "encoder.onnx"),
            decoder=os.path.join(ASR_DIR, "decoder.onnx"),
            num_threads=4, sample_rate=SR, feature_dim=80,
            decoding_method="greedy_search")
        log("流式识别就绪（sherpa-onnx，%.1fs）" % (time.time() - t0))
        return True
    except Exception as e:
        _stream_rec = None
        log("流式识别不可用: " + str(e)[:120])
        return False


def stream_reset():
    global _stream, _draft_last, _stream_last_progress, _draft_buf, _draft_owner, _draft_checked_at
    _stream = None
    _draft_last = None
    _draft_buf = []
    _draft_owner = None
    _draft_checked_at = 0.0
    _stream_last_progress = time.time()
    try:
        while True:
            _stream_q.get_nowait()
    except queue.Empty:
        pass
    push_draft("")


def push_draft(text):
    """把草稿推给 DSH 气泡（同一段不重复推）"""
    global _draft_last, _draft_at
    if text == _draft_last:
        return
    now = time.time()
    if text != "" and now - _draft_at < 0.15:
        return
    _draft_last = text
    _draft_at = now
    try:
        _post_json_with_retry("voice-draft", {"text": text}, timeout=3, tries=1)
    except Exception:
        pass


def stream_worker():
    """独立线程：只做流式识别，卡住也不会拖死主录音线程"""
    global _stream_last_progress
    while True:
        try:
            samples = _stream_q.get()
        except Exception:
            continue
        if samples is None:
            continue
        try:
            stream_feed(samples)
            if _state["armed"] and _state["in_chat"]:
                # 先判断这段声音是不是主人，不是主人的话连草稿都不显示
                try:
                    global _draft_owner, _draft_checked_at
                    now_ts = time.time()
                    total = sum(len(x) for x in _draft_buf)
                    if _draft_owner is not False and total >= int(1.2 * SR) and now_ts - _draft_checked_at > 0.8:
                        _draft_checked_at = now_ts
                        audio_all = np.concatenate(_draft_buf) if _draft_buf else np.zeros(0, dtype=np.float32)
                        ok = speaker_ok(audio_all, quiet=True)
                        if ok is False:
                            _draft_owner = False
                            push_draft("")
                        elif ok is True:
                            _draft_owner = True
                except Exception:
                    pass
                if _draft_owner is not False:
                    txt = stream_partial()
                    if txt:
                        push_draft(txt)
            _stream_last_progress = time.time()
        except Exception as _e:
            log("流式线程异常: " + str(_e)[:80])


def stream_feed(samples):
    """把一小块音频喂给流式识别器"""
    global _stream
    if _stream_rec is None:
        return
    try:
        if _stream is None:
            _stream = _stream_rec.create_stream()
        _stream.accept_waveform(SR, samples)
        try:
            _draft_buf.append(np.asarray(samples, dtype=np.float32).reshape(-1))
            if len(_draft_buf) > 400:
                _draft_buf = _draft_buf[-400:]
        except Exception:
            pass
        while _stream_rec.is_ready(_stream):
            _stream_rec.decode_stream(_stream)
    except Exception:
        pass


def stream_partial():
    """当前已识别到的文字（去掉唤醒词）"""
    if _stream_rec is None or _stream is None:
        return ""
    try:
        raw = _stream_rec.get_result(_stream).strip()
    except Exception:
        return ""
    if raw == "":
        return ""
    _, rest = strip_wake(raw)
    return rest.strip()



# ===================== 声纹（只认主人的声音） =====================
_DATA = os.path.dirname(os.path.dirname(os.path.realpath(os.path.abspath(__file__))))
SV_MODEL = os.path.join(_DATA, "asr-models", "sv", "campplus.onnx")
SV_PROFILE = os.path.join(_DATA, "voice-print.json")
_spk_ext = None
_spk_prof = None
_spk_cfg = {"enabled": False}


def init_speaker():
    global _spk_ext, _spk_prof, _spk_cfg
    try:
        import sherpa_onnx
        if not os.path.exists(SV_MODEL):
            log("声纹模型缺失，不启用声纹过滤")
            return False
        _spk_ext = sherpa_onnx.SpeakerEmbeddingExtractor(
            sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=SV_MODEL, num_threads=2))
        if os.path.exists(SV_PROFILE):
            prof = json.load(open(SV_PROFILE, encoding="utf-8"))
            _spk_prof = np.array(prof["embedding"], dtype=np.float32)
            _spk_cfg = {"enabled": prof.get("enabled", True),
                        "threshold": float(prof.get("threshold", 0.45)),
                        "min_sec": float(prof.get("min_sec", 1.2))}
            log("声纹过滤已启用（阈值 %.2f，前 %.1f 秒才判断）" % (_spk_cfg["threshold"], _spk_cfg["min_sec"]))
        else:
            log("还没有声纹档案：先用 voice-enroll.py 录一段")
        return True
    except Exception as e:
        _spk_ext = None
        log("声纹初始化失败: " + str(e)[:100])
        return False


def speaker_similarity(audio):
    if _spk_ext is None:
        return None
    try:
        s = _spk_ext.create_stream()
        s.accept_waveform(SR, audio)
        s.input_finished()
        e = np.array(_spk_ext.compute(s), dtype=np.float32)
        return float(np.dot(e, _spk_prof) / (np.linalg.norm(e) * np.linalg.norm(_spk_prof) + 1e-9))
    except Exception:
        return None


_spk_mtime = [0.0]


def _reload_profile_if_changed():
    """录入脚本刚写完档案时，不用重启也能生效"""
    global _spk_prof, _spk_cfg
    try:
        m = os.path.getmtime(SV_PROFILE)
    except Exception:
        return
    if m == _spk_mtime[0]:
        return
    try:
        prof = json.load(open(SV_PROFILE, encoding="utf-8"))
        _spk_prof = np.array(prof["embedding"], dtype=np.float32)
        _spk_cfg = {"enabled": prof.get("enabled", True),
                    "threshold": float(prof.get("threshold", 0.45)),
                    "min_sec": float(prof.get("min_sec", 1.2))}
        _spk_mtime[0] = m
        log("声纹档案已加载/更新（阈值 %.2f）" % _spk_cfg["threshold"])
    except Exception:
        pass


def speaker_ok(audio, quiet=False):
    """True=是主人；None=没法判断（放行）"""
    if _spk_ext is None:
        return None
    if _spk_prof is None or not _spk_cfg.get("enabled", False):
        _reload_profile_if_changed()
    if _spk_prof is None or not _spk_cfg.get("enabled", False):
        return None
    if len(audio) / SR < _spk_cfg.get("min_sec", 1.2):
        return None
    sim = speaker_similarity(audio)
    if sim is None:
        return None
    if not quiet:
        log("声纹相似度 %.3f（阈值 %.2f）" % (sim, _spk_cfg["threshold"]))
    return sim >= _spk_cfg["threshold"]


_lock = threading.Lock()
_state = {"armed": False, "in_chat": False, "last_voice": 0.0, "port": None, "busy": False}


def log(msg):
    line = time.strftime("%H:%M:%S") + "  " + msg
    try:
        print(line, flush=True)   # pythonw 下 stdout 为 None，必须兜住
    except Exception:
        pass
    try:
        with open(LOG, "a", encoding="utf-8-sig") as f:
            f.write(line + "\n")
    except Exception:
        pass


def find_port():
    try:
        with open(PORT_FILE, "r", encoding="utf-8") as fp:
            p = int(fp.read().strip())
            if p > 0:
                return p
    except Exception:
        pass
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq DeepSeek Harness.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=10)
        pids = set()
        for row in csv.reader(io.StringIO(out.stdout)):
            if len(row) >= 2 and row[0].strip().lower().startswith("deepseek"):
                try:
                    pids.add(int(row[1]))
                except ValueError:
                    pass
        ns = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                            encoding="utf-8", errors="ignore", timeout=20)
        for line in ns.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper() == "TCP" and "LISTENING" in parts[3]:
                try:
                    if int(parts[4]) in pids:
                        return int(parts[1].rsplit(":", 1)[1])
                except ValueError:
                    continue
    except Exception as e:
        log("端口发现失败: " + str(e))
    return None


def _post_json_with_retry(path_qs, payload, timeout=15, tries=3):
    """发一个 POST。端口失效（DSH 重启）时：重新读 host-port.txt 再试，最多 3 次。"""
    last_err = None
    for i in range(tries):
        port = find_port()          # 每次都现读文件
        if not port:
            time.sleep(0.3)
            continue
        _state["port"] = port
        url = f"http://127.0.0.1:{port}/dsh-pet-7340/{path_qs}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="ignore")
        except Exception as e:
            last_err = e
            if i < tries - 1:
                time.sleep(0.4)
    raise last_err if last_err else RuntimeError("no port")


def fresh_port():
    """每次现读 host-port.txt：DSH 重启后端口会变，不能一直用启动时那个。"""
    p = find_port()
    if p:
        _state["port"] = p
    return p or _state["port"]


def _post_say(port, text):
    """真正发一次播报请求（成功返回 True）"""
    url = f"http://127.0.0.1:{port}/dsh-pet-7340/broadcast?pet=main&surface=desktop"
    data = json.dumps({"text": text, "speak": True}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()
    return True


def speech_lines():
    try:
        with open(SPEECH, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


ANIM_LISTEN = "东张西望"          # 听到声音时：东张西望（像在听）
ANIM_THINK = "工作状态-思考冒泡"   # 生成回复时：思考冒泡


def set_anim(name):
    """让桌宠播放一个动作（失败静默）"""
    try:
        _post_json_with_retry("anim?pet=main&surface=desktop", {"name": name}, timeout=8, tries=2)
    except Exception:
        pass


def send_to_pet(text):
    """把一句话发给桌宠（走对话接口）。端口变了会自动重试。"""
    try:
        body = _post_json_with_retry("chat?pet=main&surface=desktop", {"text": text}, timeout=120)
        log("→ 桌宠: " + text)
        try:
            obj = json.loads(body)
            if not obj.get("ok"):
                log("  桌宠返回失败: " + str(obj.get("reason") or obj.get("message")))
        except Exception:
            pass
        return True
    except Exception as e:
        log("发送失败: " + str(e))
        return False


def say_to_pet(text):
    """让桌宠说一句固定的话（气泡+语音）。端口变了会自动重试。"""
    try:
        _post_json_with_retry("broadcast?pet=main&surface=desktop",
                              {"text": text, "speak": True})
        return True
    except Exception as e:
        log("播报失败: " + str(e))
        return False


def wait_for_reply(before, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if speech_lines() > before:
            time.sleep(0.8)
            return True
        time.sleep(0.2)
    return False


def fix_names(t):
    t = t.translate(T2S)
    for wrongs, right in HOMOPHONE:
        for w in wrongs:
            t = t.replace(w, right)
    return t


def strip_wake(text):
    text = text.translate(T2S)
    hit = False
    t = text
    for w in WAKE_WORDS:
        if w in t:
            hit = True
            t = t.replace(w, "", 1)
    return hit, t.strip(" ，,。.！!？?、～~")


HEARTBEAT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice-chat.heartbeat")
_MUTEX_HANDLE = None


def acquire_single_instance():
    """用一个 Windows 命名互斥体保证只有一个语音助手"""
    global _MUTEX_HANDLE
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        name = "Global\\PetVoiceChatSingleInstance"
        _MUTEX_HANDLE = kernel32.CreateMutexW(None, False, name)
        err = ctypes.get_last_error()
        if err == 183:          # ERROR_ALREADY_EXISTS
            return False
        return True
    except Exception:
        return True              # 拿不到锁就放行，至少不影响功能


def _heartbeat_loop():
    """每 20 秒刷新一次心跳文件，看门狗靠它判断存活"""
    while True:
        try:
            with open(HEARTBEAT, "w", encoding="utf-8") as f:
                f.write(str(int(time.time())))
        except Exception:
            pass
        time.sleep(20)


def start_heartbeat():
    import threading
    t = threading.Thread(target=_heartbeat_loop, daemon=True)
    t.start()


VAD_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice-vad.json")


def load_vad_cfg():
    """音量阈值配置：低于阈值的说话不算"主人说话"。
    min_rms   : 说话段的平均音量下限（0.008 ≈ -42 dBFS，底噪约 0.0009）
    min_peak  : 说话段的峰值下限
    """
    default = {"min_rms": 0.008, "min_peak": 0.05, "enabled": True}
    try:
        with open(VAD_CFG, encoding="utf-8-sig") as f:
            cfg = json.load(f)
        default.update({k: v for k, v in cfg.items() if k in default})
    except Exception:
        pass
    try:
        if not os.path.exists(VAD_CFG):
            with open(VAD_CFG, "w", encoding="utf-8") as f:
                json.dump(default, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="small")
    ap.add_argument("--device", type=int, default=None)
    ap.add_argument("--send-test", default="")
    ap.add_argument("--auto-arm", action="store_true")
    args = ap.parse_args()

    # ---- 单实例保护：已经有一个在跑就直接退出（防止看门狗重复拉起）----
    if not acquire_single_instance():
        log("已有一个语音助手在运行，本进程退出")
        return

    if args.send_test:
        log("=== 发送链路测试 ===")
        before = speech_lines()
        ok = send_to_pet(args.send_test)
        log("发送结果: " + ("成功" if ok else "失败"))
        if ok:
            log("等它出声: " + ("已出声" if wait_for_reply(before, 40) else "超时"))
        return

    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from faster_whisper import WhisperModel
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    import keyboard

    log("=== 桌宠语音对话启动 ===")
    _state["port"] = find_port()
    log(f"DSH 端口: {_state['port']}")
    log("加载识别模型…")
    vad_cfg = load_vad_cfg()
    log(f"音量阈值：rms>={vad_cfg['min_rms']} peak>={vad_cfg['min_peak']}（可在 voice-vad.json 调整）")
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=8)
    vad_opts = VadOptions(threshold=0.5, min_speech_duration_ms=300,
                          min_silence_duration_ms=400, speech_pad_ms=100)
    log("模型 + VAD 就绪")
    init_stream_asr()
    init_speaker()
    start_heartbeat()

    # 麦克风选择：只跟随 Windows 默认输入设备（在系统设置里换，程序自动跟随）
    # 需要临时指定某个设备时用 --device <编号>
    dev = args.device
    dev_src = "命令行指定"
    if dev is None:
        try:
            dev = sd.default.device[0]
            dev_src = "系统默认"
        except Exception:
            dev = None
            dev_src = "自动"
    if dev is None or dev < 0:
        devices = [(i, d) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
        if devices:
            dev = devices[0][0]
            dev_src = "自动"
    try:
        info = sd.query_devices(dev)
        name = info["name"]
        ch = info["max_input_channels"]
    except Exception:
        name, ch = "未知", 0
    log(f"麦克风 [{dev}] {name}（通道 {ch}，来源：{dev_src}）")

    q = queue.Queue()

    stream_rate = SR

    def audio_cb(indata, _frames, _t, status):
        if not (_state["armed"] and not _state["busy"]):
            return
        data = indata.copy()
        if stream_rate != SR and data.shape[0] > 0:
            try:
                import librosa
                data = librosa.resample(data[:, 0], orig_sr=stream_rate, target_sr=SR).reshape(-1, 1)
            except Exception:
                return
        q.put(data)

    def handle_transcript(text):
        hit, rest = strip_wake(text)
        with _lock:
            in_chat = _state["in_chat"]
        if not in_chat:
            if not hit:
                return
            _state["in_chat"] = True
            _state["last_voice"] = time.time()
            log("★ 唤醒")
            # 被叫名字时先应一声，让主人知道唤醒了
            try:
                say_to_pet("在的呢～主人")
            except Exception:
                pass
            if rest == "":
                return
            text = rest
        elif hit and rest != "":
            text = rest
        before = speech_lines()
        set_anim(ANIM_THINK)
        log("→ 正在思考（模型生成中）…")
        if send_to_pet(text):
            stream_reset()
            wait_for_reply(before)
            _state["last_voice"] = time.time()
            # 把"它说话期间"录到的音频丢掉，避免回声被再次识别
            try:
                while not q.empty():
                    q.get_nowait()
            except Exception:
                pass

    def worker():
        try:
            _worker_inner()
        except Exception as _e:
            import traceback
            log("worker 崩溃: " + str(_e))
            log(traceback.format_exc()[:600])

    def _worker_inner():
        pending = np.zeros(0, dtype=np.float32)
        __dbg = [0.0, 0]
        while True:
            try:
                block = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if not _state["armed"]:
                pending = np.zeros(0, dtype=np.float32)
                continue
            __dbg[1] += 1
            if time.time() - __dbg[0] > 5:
                __dbg[0] = time.time()
                try:
                    log("调试：块 %d 个/最近 rms=%.4f 队列=%d 唤醒=%s" % (
                        __dbg[1], float(np.sqrt(np.mean(block ** 2))), q.qsize(), _state["in_chat"]))
                    __dbg[1] = 0
                except Exception:
                    pass
            pending = np.concatenate([pending, block.reshape(-1)])
            # 流式识别：只入队，真正的解码在独立线程里做（防止卡死主线程）
            try:
                _stream_q.put_nowait(block.reshape(-1))
            except Exception:
                pass
            dur = len(pending) / SR
            if dur < 0.6:
                continue
            # 用 VAD 找"这段里人声在哪、末尾是否已经安静"——按自然停顿断句，不切半句
            try:
                stamps = get_speech_timestamps(pending, vad_opts)
            except Exception:
                stamps = []
            speech_sec = sum(x["end"] - x["start"] for x in stamps) / SR
            last_end = (stamps[-1]["end"] / SR) if stamps else 0.0
            tail_silence = dur - last_end if stamps else dur

            finish = False
            if speech_sec >= MIN_SPEECH_SEC and tail_silence >= 0.7:
                finish = True
            elif dur >= 12.0:
                finish = True
            elif speech_sec < 0.2 and dur >= 3.0:
                pending = pending[-SR:]        # 只保留 1 秒，丢掉无意义的静音
                continue

            if not finish:
                continue

            audio = pending[: int(min(dur, last_end + 0.3) * SR)] if stamps else pending
            pending = np.zeros(0, dtype=np.float32)
            if len(audio) / SR < MIN_SPEECH_SEC:
                continue

            # ---- 音量阈值：太轻的声音不当成"主人说话" ----
            if vad_cfg["enabled"]:
                if stamps:
                    seg_audio = np.concatenate([
                        audio[int(x["start"]): int(x["end"])] for x in stamps
                        if x["end"] > x["start"] and int(x["end"]) <= len(audio)
                    ]) if len(stamps) > 1 else audio
                else:
                    seg_audio = audio
                if len(seg_audio) == 0:
                    continue
                seg_rms = float(np.sqrt(np.mean(seg_audio ** 2)))
                seg_peak = float(np.max(np.abs(seg_audio)))
                log(f"这段音量 rms={seg_rms:.4f} peak={seg_peak:.3f}（阈值 {vad_cfg['min_rms']}）")
                if seg_rms < vad_cfg["min_rms"] or seg_peak < vad_cfg["min_peak"]:
                    log("音量太低，忽略")
                    continue
            # 声纹过滤：不是主人的声音，连唤醒都不理
            try:
                _spk = speaker_ok(audio)
                if _spk is False:
                    log("不是主人的声音，忽略")
                    continue
            except Exception:
                pass
            _state["busy"] = True
            # 保存这一句的原始录音（方便回放，听环境噪声）
            try:
                import soundfile as _sf
                _d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "input-audio")
                os.makedirs(_d, exist_ok=True)
                _fn = os.path.join(_d, time.strftime("%Y%m%d-%H%M%S") + ".wav")
                _sf.write(_fn, audio, SR)
                log("录音已保存: " + os.path.basename(_fn))
            except Exception as _e:
                log("录音保存失败: " + str(_e))
            try:
                set_anim(ANIM_LISTEN)
                t = time.time()
                segs, _ = model.transcribe(audio, language="zh", beam_size=3, vad_filter=True,
                                           initial_prompt=PROMPT, condition_on_previous_text=False,
                                           no_speech_threshold=0.6)
                text = fix_names("".join(s.text for s in segs).strip())
                if text:
                    log(f"[人声 {len(audio)/SR:.1f}s / 识别 {time.time()-t:.1f}s] {text}")
                    handle_transcript(text)
            except Exception as e:
                log("处理出错: " + str(e))
            finally:
                _state["busy"] = False

    def toggle():
        _state["armed"] = not _state["armed"]
        try:
            stream_reset()
        except Exception:
            pass
        _state["in_chat"] = False
        log("★ 开始监听" if _state["armed"] else "★ 停止监听")
        # 用语音告诉你当前状态（不经过模型，立刻出声）
        if _state["armed"]:
            threading.Thread(target=say_to_pet, args=("主人，我听着呢",), daemon=True).start()
        else:
            threading.Thread(target=say_to_pet, args=("小嘴巴，闭起来",), daemon=True).start()

    if args.auto_arm:
        _state["armed"] = True
        log("★ 自动进入监听（自测模式）")

    keyboard.add_hotkey("f9", toggle)
    keyboard.add_hotkey("ctrl+f10", lambda: (log("按 Ctrl+F10 退出"), os._exit(0)))
    log("按 F9 开始/停止监听（Ctrl+F10 退出程序）")

    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=stream_worker, daemon=True).start()
    try:
        stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", device=dev, callback=audio_cb)
        stream.start()
        stream_rate = SR
    except Exception as e:
        # 设备不支持 16k（很多阵列只支持 48k），改用设备默认采样率并重采样
        try:
            info2 = sd.query_devices(dev)
            stream_rate = int(info2.get("default_samplerate") or 48000)
        except Exception:
            stream_rate = 48000
        log(f"16kHz 打不开（{e}），改用 {stream_rate}Hz 并重采样")
        stream = sd.InputStream(samplerate=stream_rate, channels=1, dtype="float32", device=dev, callback=audio_cb)
        stream.start()
    try:
        while True:
            time.sleep(0.5)
            if _state["in_chat"] and time.time() - _state["last_voice"] > CHAT_IDLE_TIMEOUT:
                _state["in_chat"] = False
                log("对话超时，回到等待唤醒")
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        stream.close()


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        log("!!! 崩溃 !!!")
        log(traceback.format_exc())
        raise
