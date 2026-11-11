param(

  [string]$Clip = '',

  [double]$Start = 1,

  [double]$Volume = 0.2,

  [int]$FadeMs = 3500,

  [int]$HoldMs = 0,

  [int]$DurationMs = 3000

)

$logPath = Join-Path $PSScriptRoot 'bgm.log'

function BgmLog($m) {

  try { Add-Content -LiteralPath $logPath -Value ((Get-Date -Format 'HH:mm:ss') + ' ' + $m) -Encoding UTF8 } catch {}

}

if ($Clip -eq '' -or -not (Test-Path -LiteralPath $Clip)) { BgmLog 'clip missing'; exit 0 }

Add-Type -AssemblyName PresentationCore

Add-Type -AssemblyName WindowsBase

function Pump([int]$ms) {

  $frame = New-Object System.Windows.Threading.DispatcherFrame

  $timer = New-Object System.Windows.Threading.DispatcherTimer

  $timer.Interval = [TimeSpan]::FromMilliseconds([math]::Max(10, $ms))

  $script:pumpTimer = $timer

  $timer.Add_Tick({ $script:pumpTimer.Stop(); $frame.Continue = $false })

  $timer.Start()

  [System.Windows.Threading.Dispatcher]::PushFrame($frame)

}

try {

  $player = New-Object System.Windows.Media.MediaPlayer

  $player.Open([uri]$Clip)

  BgmLog ('open: ' + $Clip)

} catch {

  BgmLog ('open failed: ' + $_.Exception.Message)

  exit 0

}

$waited = 0

while ($waited -lt 5000) {

  if ($player.NaturalDuration.HasTimeSpan) { break }

  Pump 100

  $waited += 100

}

$dur = 0

try { if ($player.NaturalDuration.HasTimeSpan) { $dur = $player.NaturalDuration.TimeSpan.TotalSeconds } } catch {}

BgmLog ('opened dur=' + $dur)

try { $player.Position = [TimeSpan]::FromSeconds($Start) } catch {}

$vol = [double][math]::Min(1.0, [double][math]::Max(0.0, [double]$Volume))

try { $player.Volume = $vol } catch {}

try { $player.Play() } catch { BgmLog ('play failed: ' + $_.Exception.Message) }

BgmLog ('playing vol=' + $vol + ' start=' + $Start)

$elapsed = 0

while ($elapsed -lt ($DurationMs + $HoldMs)) { Pump 100; $elapsed += 100 }

$fadeStart = $elapsed

while ($elapsed -lt ($fadeStart + $FadeMs)) {

  $k = 1 - (($elapsed - $fadeStart) / [double][math]::Max(1, $FadeMs))

  if ($k -le 0) { break }

  try { $player.Volume = $vol * $k } catch {}

  Pump 80

  $elapsed += 80

}

try { $player.Stop() } catch {}

try { $player.Close() } catch {}

BgmLog 'done'

exit 0

