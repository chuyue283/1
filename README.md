# 桌面陪伴宠物「小鱼 / 鲸娘」

一个跑在 **DeepSeek Harness (DSH)** 上的桌面宠物项目：本地大模型驱动、双人格、语音输入输出、记忆与声纹。

> 全部代码由「人提需求 + AI 写代码」协作完成，真实对话记录见 [`docs/ai-collaboration-log.md`](docs/ai-collaboration-log.md)。

---

## 1. 它是什么

- **看得见的桌宠**：DSH 插件 `dsh-pet` 渲染 2D 角色，有动画、气泡、右键菜单。
- **双人格**
  - 小鱼：3B 模型，软、黏人、句子短
  - 鲸娘：7B 模型，姐姐人格，傲娇、会吃小鱼的醋、会学小鱼说话
  - 代码拦截切换词：`鲸娘` / `小鱼，叫那个姐姐出来` / `让小鱼出来吧`
- **记忆**：聊天全量落盘 + 向量检索；鲸娘能看到小鱼的对话，小鱼看不到鲸娘的（单向可见）。
- **语音输出**：Fish Audio TTS，按人格切音色，开机问候带 BGM。
- **语音输入**：麦克风常驻监听、唤醒词、流式识别（边说边出字）、声纹只认主人。
- **本地化**：Ollama 本地模型，全部数据放在 `D:\...\dsh-pet-data`，不依赖云。

## 2. 架构

```
麦克风 ──► voice-chat.py ──► DSH 插件(dsh-pet) ──► Ollama(3B/7B)
              │  │                    │
              │  └─ 流式识别(sherpa)  ├─ 记忆检索(bge-m3 向量 + 关键词)
              │      └─ 气泡草稿      ├─ 人格引擎(切换/开场白/抱怨)
              │                       └─ 回复文本
              │                              │
              └─ 声纹过滤(CAM++)            ▼
                                     voice_daemon.py ──► Fish TTS ──► 播放
```

细节见 [`docs/architecture.md`](docs/architecture.md)。

## 3. 目录

```
src/                本项目自己写的代码
  voice-chat.py       语音输入主程序（唤醒 / VAD / 流式识别 / 声纹 / 发送）
  voice_daemon.py     语音守护进程（TTS 合成 + 缓存 + 播放 + BGM）
  voice-enroll.py     声纹录入
  voice-watchdog.py   健康监测
  bgm.ps1             问候背景音乐播放器
  backup-config.ps1   每日配置/记忆快照
  start-ollama.ps1    开机拉起 Ollama（模型目录指向 D 盘）
patches/            对上游 dsh-pet 0.3.8 的定制补丁（unified diff）
configs/            配置模板（脱敏）
docs/               架构、核心迭代、AI 协作记录、排错、演示脚本
```

## 4. 依赖

| 依赖 | 用途 |
|---|---|
| DeepSeek Harness | 宿主应用（Electron） |
| dsh-pet 0.3.8 | 桌宠插件（MIT），本项目在其上打补丁 |
| Ollama | 本地模型运行时 |
| 模型：`qwen2.5:3b-instruct` / `qwen2.5:7b-instruct` / `bge-m3` | 两个人格 + 向量检索 |
| sherpa-onnx + paraformer / CAM++ | 流式中文识别 / 声纹 |
| faster-whisper (small) | 最终精修识别 |
| Fish Audio API | TTS（需自备 Key） |
| Python 3.12 | 运行脚本（DSH 自带运行时即可） |

`requirements.txt` 见根目录。

## 5. 十分钟复现

```powershell
# 1) 目录约定（可改，改完记得同步脚本里的路径）
#    D:\桌面\dafeiyu\dsh-pet-data\        数据根：模型 / 语料 / 缓存 / 脚本
#    C:\Users\<你>\.dsh\profiles\desktop   DSH 配置目录

# 2) 环境变量（用户级）
setx OLLAMA_MODELS "D:\桌面\dafeiyu\dsh-pet-data\models"
setx OLLAMA_KEEP_ALIVE -1
setx OLLAMA_MAX_LOADED_MODELS 4

# 3) 拉模型
ollama pull qwen2.5:3b-instruct
ollama pull qwen2.5:7b-instruct
ollama pull bge-m3

# 4) 安装 Python 依赖（DSH 自带 python 即可）
python -m pip install faster-whisper sherpa-onnx sounddevice librosa soundfile numpy requests

# 5) 下载 ASR / 声纹模型（见 docs/voice-input.md 的下载地址），放到
#    dsh-pet-data\asr-models\paraformer\ 与 asr-models\sv\campplus.onnx

# 6) 给插件打补丁
cd C:\Users\<你>\.dsh\profiles\desktop\node_modules\dsh-pet
git apply --ignore-space-change D:\path\to\pet-competition\patches\dsh-pet-index.patch
git apply --ignore-space-change D:\path\to\pet-competition\patches\dsh-pet-client.patch

# 7) 配置
#    把 configs/voice.example.json 复制到 dsh-pet-data\voice.json 并填 Fish Key
#    fish-key.txt 放同一目录（文件里只写 Key 本身）

# 8) 启动
#    先开 Ollama，再开 DSH；语音助手可手动运行：
python src\voice-chat.py
```

更细的排错见 [`docs/troubleshooting.md`](docs/troubleshooting.md)。

## 6. 已知限制

- 声纹只对 ≥1.2 秒的语句生效；音色相近的家人可能通过。
- 流式识别（paraformer 14M/paraformer-zh）准确率低于 whisper small，气泡里是草稿，发送前会用 whisper 精修。
- 7B 在无独显的机器上约 4–6 token/s，首句延迟 5–9 秒，属于硬件上限。
- 问候语 BGM、语音缓存等依赖本地代理访问 Fish Audio。

## 7. License

本项目代码 MIT。上游 `dsh-pet` 为 MIT（Copyright (c) 2026 PC2005-cloud），补丁与说明中保留其版权声明。
