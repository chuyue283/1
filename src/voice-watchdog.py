"""语音助手看门狗（重写版）

之前的问题：
    用 WMIC 解析进程命令行 → 解析失败 → 以为没在跑 → 每 2 分钟拉一个新的
    → 11 个进程 × 340MB = 3.6GB 内存被吃光

现在改成看"心跳文件"：
    voice-chat.py 每 20 秒刷新一次 voice-chat.heartbeat
    心跳在 90 秒内 → 认为在运行
    否则 → 启动一个（voice-chat 自己有单实例锁，不会重复）
"""
import datetime
import os
import subprocess
import time

CREATE_NO_WINDOW = 0x08000000
PYW = r"C:\Users\Chinagay\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe"
TARGET = r"D:\dsh-tools\voice-chat.py"
HEARTBEAT = r"D:\dsh-tools\voice-chat.heartbeat"
LOG = r"D:\dsh-tools\voice-watchdog.log"
INTERVAL = 60
STALE_SECONDS = 90


def log(msg):
    try:
        line = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "  " + msg
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def heartbeat_age():
    try:
        return time.time() - os.path.getmtime(HEARTBEAT)
    except OSError:
        return 10 ** 9


def start_target():
    try:
        subprocess.Popen([PYW, TARGET], creationflags=CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True)
        return True
    except Exception as e:
        log("启动失败：" + str(e))
        return False


def main():
    log("看门狗启动（心跳模式，每 %d 秒检查）" % INTERVAL)
    misses = 0
    while True:
        try:
            age = heartbeat_age()
            if age <= STALE_SECONDS:
                misses = 0
            else:
                misses += 1
                if misses >= 2:
                    log("心跳已停 %.0f 秒，拉起语音助手" % age if age < 100000 else "没有心跳文件，拉起语音助手")
                    if start_target():
                        misses = 0
        except Exception as e:
            log("检查出错：" + str(e))
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
