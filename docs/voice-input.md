# 语音输入与声纹

## 1. 链路

```
麦克风(16k) → 分块 → VAD 断句（说话≥0.6s + 静音≥0.7s）
   │                    │
   │                    ├─ 流式识别(paraformer) → 草稿气泡
   │                    └─ 声纹(CAM++) → 不是主人就丢弃
   ▼
whisper small 精修 → 唤醒词判断 → 发送给 DSH 插件
```

## 2. 组件与模型

| 用途 | 组件 | 体积 | 下载 |
|---|---|---|---|
| 流式识别 | sherpa-onnx + streaming paraformer zh | 636MB + 228MB | `csukuangfj/sherpa-onnx-streaming-paraformer-zh` |
| 精修识别 | faster-whisper small (int8) | ~480MB | 自动下载 |
| 声纹 | CAM++ (3D-Speaker) | 28MB | `csukuangfj/speaker-embedding-models` |

放置位置：

```
dsh-pet-data\asr-models\paraformer\{tokens.txt,encoder.onnx,decoder.onnx}
dsh-pet-data\asr-models\sv\campplus.onnx
```

## 3. 唤醒

- 唤醒词：`小鱼` / `小女仆` / `蓝毛小女仆`（含同音修复：小于/小语/小玉…）
- 唤醒后 45 秒内不用再喊（`CHAT_IDLE_TIMEOUT`）
- 唤醒本身不弹气泡；唤醒后才开始推流式草稿

## 4. 草稿气泡

`voice-chat.py` 每 0.15 秒把当前识别文字 POST 到：

```
POST /dsh-pet-7340/voice-draft   {"text": "..."}
```

宿主收到后写进宠物 `say` 气泡（`silent: true`，不出声），所以复用了她说话时的同一个气泡，不需要额外客户端 UI。

结束时：

```
POST {"text": ""}  → 清空草稿
```

## 5. 声纹

```powershell
# 录入（4 段 × 4 秒）
python src\voice-enroll.py
# 检查
python src\voice-enroll.py --check
```

- 档案：`dsh-pet-data\voice-print.json`
- 阈值默认 0.45；相似度 < 阈值 → 日志「不是主人的声音，忽略」
- 短于 1.2 秒不判断（放行）
- 没有档案时不过滤

**实测**：主人自己 0.69–0.82；vs 合成音 0.002–0.126。

## 6. 常见调参

| 参数 | 位置 | 作用 |
|---|---|---|
| `min_rms` / `min_peak` | `voice-vad.json` | 音量门槛，太低会收进环境音 |
| `threshold` | `voice-print.json` | 声纹阈值，误拒就调低 |
| `min_sec` | `voice-print.json` | 多短的话不做声纹判断 |
| `CHAT_IDLE_TIMEOUT` | `voice-chat.py` | 唤醒保持时长 |
