# 每天给桌宠做一次快照（配置 + 事实记忆 + 聊天记忆库），只保留最近 N 天
$ErrorActionPreference = 'Continue'
$KeepDays = 7
$srcDir  = 'C:\Users\Chinagay\.dsh\dsh-pet'
$dstDir  = 'D:\桌面\dafeiyu\dsh-pet-data\backup\config'
$logFile = Join-Path $dstDir 'backup.log'
New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
function Log($msg) {
    $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $msg
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}
Log '=== 快照开始 ==='
$items = @(
    @{ Rel = 'main-config.jsonc';         Name = 'main-config.jsonc' },
    @{ Rel = 'memory.json';               Name = 'memory.json' },
    @{ Rel = 'standalone-runtime.json';   Name = 'standalone-runtime.json' },
    @{ Rel = 'voice\corpus\facts.json';   Name = 'facts.json' },
    @{ Rel = 'voice\corpus\memory.jsonl'; Name = 'memory.jsonl' }
)
foreach ($it in $items) {
    $src = Join-Path $srcDir $it.Rel
    if (Test-Path $src) {
        $dst = Join-Path $dstDir ($stamp + '_' + $it.Name)
        try {
            Copy-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop
            $size = (Get-Item $dst).Length
            Log ("复制 " + $it.Name + " -> " + (Split-Path $dst -Leaf) + " (" + $size + " 字节)")
        } catch {
            Log ("复制失败 " + $it.Name + ": " + $_.Exception.Message)
        }
    } else {
        Log ("跳过（不存在）" + $it.Rel)
    }
}
$cut = (Get-Date).AddDays(-$KeepDays)
$old = Get-ChildItem -LiteralPath $dstDir -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\d{8}-\d{6}_' -and $_.LastWriteTime -lt $cut }
foreach ($o in $old) {
    try { Remove-Item -LiteralPath $o.FullName -Force -ErrorAction Stop; Log ("清理旧快照 " + $o.Name) } catch { Log ("清理失败 " + $o.Name) }
}
$snap = Get-ChildItem -LiteralPath $dstDir -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\d{8}-\d{6}_' }
$total = ($snap | Measure-Object Length -Sum)
Log ("=== 完成，保留 " + $KeepDays + " 天；快照 " + $snap.Count + " 个文件，共 " + [math]::Round($total.Sum/1MB, 2) + " MB ===")
