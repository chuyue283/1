# 启动语音助手（单实例）
$py = 'C:\Users\Chinagay\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe'
$script = Join-Path $PSScriptRoot '..\src\voice-chat.py'
Start-Process -FilePath $py -ArgumentList ('"' + (Resolve-Path $script) + '"') -WindowStyle Hidden
Write-Host '语音助手已启动'
