# Copy the project (and your known/ photos) from this PC to the Pi, optionally run setup.
#   .\deploy.ps1                 # copy only
#   .\deploy.ps1 -Setup          # copy + bash setup_pi.sh
#   .\deploy.ps1 -Pi ijun@192.168.137.220
param([string]$Pi = "rpi5", [string]$Dest = "security_cam", [switch]$Setup)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$items = @("app.py", "seccam", "tools", "config.json", "requirements.txt", "setup_pi.sh", "run.sh") +
         @("known", "config.local.json" | Where-Object { Test-Path $_ })
$tar = Join-Path $env:TEMP "seccam_deploy.tar"
tar --exclude "__pycache__" -cf $tar @items
if ($LASTEXITCODE) { throw "tar failed" }
ssh $Pi "mkdir -p ~/$Dest"
scp -q $tar "${Pi}:~/$Dest/.deploy.tar"
ssh $Pi "cd ~/$Dest && tar -xf .deploy.tar && rm .deploy.tar && sed -i 's/\r$//' setup_pi.sh run.sh && chmod +x setup_pi.sh run.sh && ls"
Remove-Item $tar
if ($Setup) { ssh -t $Pi "cd ~/$Dest && bash setup_pi.sh" }
Write-Host "deployed to ${Pi}:~/$Dest"
