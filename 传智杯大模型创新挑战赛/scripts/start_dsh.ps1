# 启动 DSH（如已开机自启可跳过）
$cmd = 'D:\桌面\重启DSH.cmd'
if (Test-Path $cmd) { Start-Process -FilePath $cmd } else { Write-Host '未找到重启脚本，请手动启动 DSH' }
