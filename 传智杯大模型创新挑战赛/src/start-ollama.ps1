# 开机自启 Ollama（模型目录指向 D 盘，模型常驻不卸载）
# 由注册表 HKCU\...\Run 在登录时调用，独立于 DSH：
#   · DSH 退出 → 它不受影响
#   · 关机/注销 → 进程随会话结束
# 如果已经在运行，就直接跳过（不会起第二个实例抢端口）。

$ErrorActionPreference = 'Continue'

$exe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
$models = 'D:\桌面\dafeiyu\dsh-pet-data\models'
$log = 'D:\dsh-tools\ollama-boot.log'

function Write-Log($m) {
  try { Add-Content -LiteralPath $log -Value ((Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + '  ' + $m) -Encoding UTF8 } catch {}
}

Write-Log '--- boot launcher start ---'

if (-not (Test-Path -LiteralPath $exe)) { Write-Log "找不到 $exe"; exit 1 }

# 已经在跑就什么都不做
try {
  $r = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
  Write-Log '已有实例在运行，跳过'
  exit 0
} catch {}

# 模型目录：优先用真实路径（Ollama 不认目录联接）
if (-not (Test-Path -LiteralPath $models)) {
  $alt = 'C:\Users\Chinagay\.dsh\dsh-pet\voice\models'
  if (Test-Path -LiteralPath $alt) { $models = $alt }
}

$env:OLLAMA_MODELS = $models
$env:OLLAMA_KEEP_ALIVE = '-1'
$env:OLLAMA_HOST = '127.0.0.1:11434'

try {
  $p = Start-Process -FilePath $exe -ArgumentList 'serve' -WindowStyle Hidden -PassThru
  Write-Log ("已启动 pid=" + $p.Id + " models=" + $models)
} catch {
  Write-Log ('启动失败: ' + $_.Exception.Message)
  exit 1
}

# 等它就绪（最多 20 秒），方便日志里确认
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 500
  try {
    $r = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
    Write-Log ("就绪，模型: " + (($r.models | Select-Object -ExpandProperty name) -join ', '))
    exit 0
  } catch {}
}
Write-Log '启动后 20 秒仍未就绪'
exit 2
