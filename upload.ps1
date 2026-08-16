# upload.ps1 - sincroniza arquivos .py .json .html para ESP32 via mpremote (incremental)
param(
  [string]$port = "COM3"
)

$root = (Get-Location).Path
$tempFolder = Join-Path $env:TEMP ("mpremote_tmp_{0}" -f (Get-Random))
New-Item -Path $tempFolder -ItemType Directory | Out-Null

# detecta python/py e configura chamada para mpremote (usa python -m mpremote quando necessário)
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pyLauncher) {
  $exe = $pyLauncher.Source
  $baseArgs = "-3","-m","mpremote"
} elseif ($pythonCmd) {
  $exe = $pythonCmd.Source
  $baseArgs = "-m","mpremote"
} else {
  Write-Error "Python não encontrado. Instale Python e mpremote (py -3 -m pip install --user mpremote)."
  exit 1
}

function Invoke-MpRemote {
  param([string[]]$mpArgs)
  $all = $baseArgs + $mpArgs
  & $exe @all
  return $LASTEXITCODE
}

Get-ChildItem -Path $root -Recurse -Include *.py,*.json,*.html -File | ForEach-Object {
  $local = $_.FullName
  $rel = $local.Substring($root.Length+1) -replace '\\','/'
  $remote = $rel
  $tmpLocal = Join-Path $tempFolder $_.Name

  Invoke-MpRemote -mpArgs @("connect",$port,"fs","get",$remote,$tmpLocal) > $null 2>$null
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $tmpLocal)) {
    Write-Host "Uploading new: $rel"
    $dir = Split-Path $remote -Parent
    if ($dir -ne '') { Invoke-MpRemote -mpArgs @("connect",$port,"fs","mkdir",$dir) > $null 2>$null | Out-Null }
    Invoke-MpRemote -mpArgs @("connect",$port,"fs","put",$local,$remote)
  } else {
    $localHash = (Get-FileHash -Algorithm MD5 $local).Hash
    $remoteHash = (Get-FileHash -Algorithm MD5 $tmpLocal).Hash
    if ($localHash -ne $remoteHash) {
      Write-Host "Updating changed: $rel"
      Invoke-MpRemote -mpArgs @("connect",$port,"fs","put",$local,$remote)
    } else {
      Write-Host "Skipping identical: $rel"
    }
    Remove-Item $tmpLocal -ErrorAction SilentlyContinue
  }
}

Remove-Item -Recurse -Force $tempFolder
Write-Host "Reiniciando ESP32..."
Invoke-MpRemote -mpArgs @("connect",$port,"reset")
Write-Host "Upload concluído."