# 02 · 脚本清单（dsh-tools）

> 路径：`D:\桌面\dafeiyu\dsh-pet-data\dsh-tools`
> 这个目录通过 junction 映射到 `D:\dsh-tools`，两个路径指向同一份文件。
> 带 `_` 开头的是**临时补丁脚本**，跑过一次就没用了，可以删。

---

## 一、语音相关（日常使用）

| 脚本 | 作用 | 怎么用 |
|---|---|---|
| `voice-chat.py` | **语音对话主程序**：监听麦克风 → Whisper 识别 → 发给桌宠 → 她回答 | 按 F9 开始/停止，Ctrl+F10 退出 |
| `voice-chat.cmd` | 启动上面的程序（双击） | ✅ 常用 |
| `start-voice.cmd` / `stop-voice.cmd` / `status-voice.cmd` | 启动 / 停止 / 看状态 | ✅ 常用 |
| `voice-watchdog.py` | **健康监测**：voice-chat 挂了自动拉起 | 后台常驻 |
| `voice-watchdog.ps1` | 旧版健康监测（PowerShell） | ⚠️ 已被 py 版替代 |
| `voice-vad.json` | **音量阈值配置**：低于这个音量不算主人说话 | 改完重启 voice-chat |
| `voicectl.ps1` | 语音总控（启动/停止/状态） | 内部调用 |
| `toggle-speech.cmd` | 开关她的语音 | ✅ |
| `voice-test.cmd` | 测试语音链路 | ✅ 排查用 |
| `voice-input.py` | 早期录音测试脚本 | ⚠️ |
| `input-audio\` | **你说话**的录音（排查噪声用），每句一个 wav | 定期清理 |
| `voice-chat.log` | 语音助手日志 | 看识别结果 |
| `voice-chat.heartbeat` | 心跳文件（健康监测判断存活） | 自动生成 |

---

## 二、歌曲相关

| 脚本 | 作用 |
|---|---|
| `song-listener.py` | **监听播放**：检测你在听什么歌，记录播放次数 |
| `startSongs.cmd` / `stopSongs.cmd` | 启动 / 停止监听 |
| `songs.py` | 歌曲工具主库（时长限制、状态写入） |
| `songs-ctl.ps1` | 歌曲服务控制 |
| `songs-canon.py` | 规范歌名（去版本号、统一写法） |
| `songs-clean.py` | 清洗曲库（歌手名、异常时长） |
| `songs-rank.py` | 生成喜好榜 `favorites.json` |
| `run-rank.cmd` | 双击生成喜好榜 |
| `show-favorites.py` | 显示当前喜好榜 |
| `showFavorites.cmd` | 双击查看喜好榜 |
| `listSongs.cmd` | 列出曲库 |
| `addSong.cmd` | 添加歌曲 |
| `fetchLyrics.cmd` / `pickLyrics.cmd` | 抓歌词 / 选歌词 |
| `kugou_title.py` | 从酷狗文件名提取歌名 |
| `sing.py` / `sing2.py` | 唱歌相关实验脚本 |

---

## 三、拼接连发语音（实验项目，未接入桌宠）

| 脚本 | 作用 |
|---|---|
| `syllable_bank.py` / `syllable_concat.py` | 单字音节库 / 拼接 |
| `phrase_bank.py` / `phrase_add.py` | 短语库 / 添加短语 |
| `word_bank.py` | 词库（两字/三字/四字） |
| `title_bank.py` | 歌名音频库 |
| `particle_extract.py` / `particle_extract2.py` | 虚词提取（放慢→切→恢复） |
| `particle_lib.py` | 虚词进情绪库 |
| `emotion_bank.py` | 情绪素材库（开心/平淡/难过） |
| `emotion_rebuild.py` | 按情绪重建素材库 |
| `pinyin_word_tts.py` | 拼音作索引的 TTS |
| `concat_v2/v3/v4.py` / `concat_emo.py` | 不同版本的拼接器 |
| `voice-concat*.py` | 更早的拼接实验 |
| `pitchify.py` / `pitchify2.py` | 音高调整实验 |

---

## 四、备份与恢复

| 脚本 | 作用 |
|---|---|
| `backup-config.ps1` | **每天 12:00 快照**配置+事实+记忆（计划任务 PetConfigBackup 调用） |
| `backup-data.ps1` / `backup-data.cmd` | 整包备份数据到 backup\ |
| `backup-plugin.cmd` | 备份插件 |
| `restore-plugin.cmd` | 恢复插件 |
| `showMemory.cmd` / `show-memory.py` | 查看记忆 |
| `clean.cmd` / `clean-services.ps1` | 清理临时文件/服务 |
| `_recover.ps1` / `_recover2.ps1` | 2026-11-07 搬家事故的恢复脚本（已用完，可删） |

---

## 五、系统调优

| 脚本 | 作用 |
|---|---|
| `sys-tune.ps1` / `sys-tune-all.cmd` | 系统调优（电源/性能/虚拟内存） |
| `sys-tune-pagefile.cmd` / `sys-tune-cleanup.cmd` | 页面文件相关 |
| `fix-pagefile.ps1` / `fix-pagefile.cmd` / `fix-pagefile-reset.cmd` | 修复虚拟内存 |
| `raise-pagefile.ps1/.cmd` | 提高虚拟内存 |
| `set-pagefile-e.ps1/.cmd` | 把虚拟内存设到 E 盘 |
| `start-ollama.ps1` | 启动 Ollama |
| `pet-standalone.ps1` / `startPetStandalone.cmd` / `pet-standalone-stop.cmd` / `pet-standalone-status.cmd` | 独立启动桌宠（不依赖 DSH） |

---

## 六、临时补丁（可以删）

`_patch_*.py`、`_patch_*.yml`、`_identity_*.js`、`_persona_*.js`、`_pronoun_fn.js`、`_rounds_fn.js`、`_vecmem_fn.js`、`_check_plugins.ps1`、`_pyprocs.ps1`、`_deep_path.txt`、`_security_events.txt`

**这些都是历史补丁/临时文件，功能已并入插件，删掉不影响使用。**

---

## 七、测试脚本（可以删）

`test-*.mjs`、`judge-bench*.py`、`single_char_test*.py`、`asr-sample.mp3`、`*.wav`（A-/B-/C- 开头那些）

**都是实验时的测试文件。**

---

## 八、日志（可以清空）

`voice-chat.log`、`voice-watchdog.log`、`standalone.log`、`standalone.err.log`、`ollama-boot.log`、`voice-in.log`

**出问题的时候才需要看。**
