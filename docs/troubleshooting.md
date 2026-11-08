# 04 · 常见问题

## Q1：她只出文字没声音，怎么办？

按顺序查：

1. **看守护日志**：`corpus\daemon.log`
   - 没有新行 → 插件没启动守护进程（插件代码问题）
   - 有"合成失败 HTTP xxx" → Fish 接口/代理问题
2. **看代理是否开着**：FlClash 必须在运行（Fish 要出网）
3. **看 fish-key**：`fish-key.txt` 是否为空
4. **看说话记录**：`corpus\speech.jsonl` 最后一条
   - `"played": true` → 播过了（可能你静音了系统音量）
   - `"error": "synth-failed"` → 合成失败

---

## Q2：她说话的声音存在哪？

| 内容 | 位置 |
|---|---|
| 音频文件（mp3） | `voice-cache\*.mp3`（按文本哈希命名，不是按时间） |
| 文字记录 | `corpus\speech.jsonl`（时间、音色、文本、是否播放成功） |

**想按日期保存她的语音** → 需要一个额外功能（每次播放时另存一份到 `voice-history\日期\`），现在没有开启，需要的话告诉开发方。

---

## Q3：记忆存在哪？怎么看？

| 内容 | 位置 |
|---|---|
| 聊天记忆（全部） | `corpus\memory.jsonl` |
| 事实记忆（名字/电话/生日） | `corpus\facts.json` |
| 向量索引 | `corpus\memory-vectors.jsonl` |
| 每天快照 | `backup\config\`（保留 7 天） |

**用记事本直接打开 memory.jsonl 就能看**，一行一条。

---

## Q4：怎么切换鲸娘 / 小鱼？

| 说法 | 效果 |
|---|---|
| 鲸娘 | 切到第二人格（7B、御姐音色） |
| 小鱼，叫那个姐姐出来 | 同上 |
| 小鱼，把姐姐叫出来 | 同上 |
| 让小鱼出来吧 | 切回第一人格（只在鲸娘状态有效） |

**切换时会播动作**（屈膝礼仪 / 原地小憩）。

---

## Q5：为什么她记不得鲸娘期间的事？

这是设计：

- **小鱼**：看不到鲸娘期间的对话（失忆）
- **鲸娘**：能看到小鱼期间的一切，并且知道那是小鱼的

人格标签存在 `memory.jsonl` 的 `who` 字段里。

---

## Q6：模型在哪？能不能换？

- 目录：`models\blobs`（Ollama 管理）
- 环境变量：`OLLAMA_MODELS = D:\桌面\dafeiyu\dsh-pet-data\models`
- 换模型：`ollama pull xxx`，然后在 `main-config.jsonc` 里改 `chatModel`

---

## Q7：搬家/换路径要注意什么？

**这个目录里有两个 junction（链接）**：

```
C:\Users\<用户>\.dsh\dsh-pet   →  D:\桌面\dafeiyu\dsh-pet-data\dsh-pet-config
D:\dsh-tools                   →  D:\桌面\dafeiyu\dsh-pet-data\dsh-tools
```

**移动目录之前**：先删掉这两个链接（`cmd /c rmdir 路径`），再搬真实文件，搬完重建链接。

**2026-11-07 的事故就是没删链接**：`dsh-pet\voice` 是指向整个数据目录的链接，移动时被展开，造成递归复制、丢了 `daemon.ps1`。

---

## Q8：怎么确认一切正常？

```powershell
# 1. 人格状态
Get-Content D:\桌面\dafeiyu\dsh-pet-data\persona.json

# 2. 模型是否常驻
curl http://127.0.0.1:11434/api/ps

# 3. 语音守护日志
Get-Content D:\桌面\dafeiyu\dsh-pet-data\corpus\daemon.log -Tail 10

# 4. 最近说话记录
Get-Content D:\桌面\dafeiyu\dsh-pet-data\corpus\speech.jsonl -Tail 3

# 5. 每天备份是否在跑
Get-ScheduledTask -TaskName PetConfigBackup
```

---

## Q9：哪些文件绝对不能删？

```
corpus\memory.jsonl
corpus\facts.json
corpus\speech.jsonl
songs\library.jsonl
songs\favorites.json
dsh-pet-config\main-config.jsonc
voice.json
fish-key.txt
voice_daemon.py
dsh-tools\voice-chat.py
按钮\（全部）
```
