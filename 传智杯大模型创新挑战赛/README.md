# 硅基生命计划

一个运行在 DeepSeek Harness 上的桌面陪伴型 AI 生命体，具备双人格、长期记忆、语音对话、声纹识别与长篇写作能力。项目已经完成本地模型部署、语音输入输出、人格切换、记忆检索、长篇朗读与运维脚本。

## 项目简介

项目目标是构建一个长期陪伴、记得住事、有自己性格的桌面 AI。它不是一次性的问答页面，而是常驻桌面的角色：能听、能说、有人格、有记忆，并且全部推理与语音都在本地完成。

评委可以通过桌面上的角色直接看到：语音唤醒、双人格切换、记忆回忆、声纹过滤、长篇写作与朗读。

## 技术栈

- 宿主：DeepSeek Harness（Electron）+ dsh-pet 插件
- 模型：Ollama、qwen2.5:3b-instruct、qwen2.5:7b-instruct、bge-m3
- 语音输入：faster-whisper、sherpa-onnx 流式识别、Silero VAD
- 声纹：CAM++（3D-Speaker）
- 语音输出：Fish Audio TTS、本地发声进程
- 工程：Python、PowerShell、Windows 计划任务

## 功能列表

- 双人格：小鱼（3B，软萌）与小岚（7B，姐姐），代码拦截切换
- 单向记忆：小岚记得小鱼说过的话，小鱼不记得小岚
- 分层记忆：最近对话 + 向量检索 + 时间检索 + 每日印象
- 语音输入：唤醒词、断句、流式草稿、声纹过滤
- 语音输出：按人格切音色、缓存、开机问候带 BGM
- 长篇写作：日记、情书、故事，边写边念，全文单独存档
- 自我纠错：答非所问时补一句，只补一次
- 运维：一键重启、每日备份、进程看门狗

## 启动方式

### 1. 启动本地模型

```powershell
ollama serve
ollama pull qwen2.5:3b-instruct
ollama pull qwen2.5:7b-instruct
ollama pull bge-m3
```

### 2. 启动 DSH 与桌宠

```powershell
.\scripts\start_dsh.ps1
```

### 3. 启动语音助手

```powershell
.\scripts\start_voice.ps1
```

### 4. 录入声纹（首次）

```powershell
python .\src\voice-enroll.py
```

### 验证命令

```powershell
python -m py_compile .\src\voice-chat.py .\src\voice_daemon.py
```

## 演示文件说明

- 声纹录音：`demo_files/voice-sample.wav`（可自行录制）
- 长篇示例：运行后写入数据目录 `corpus/longform.jsonl`
- 记忆示例：数据目录 `corpus/memory.jsonl`
- 配置模板：`configs/voice.example.json`、`configs/env.example`

## 目录结构

```
├── src/            语音输入、发声、声纹、运维脚本
├── patches/        对上游 dsh-pet 的定制补丁
├── configs/        脱敏配置模板
├── scripts/        启动脚本
├── docs/           架构、流程、演示脚本
├── demo_files/     演示素材
└── 作品介绍文档.docx
```
