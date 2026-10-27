# deploy_files.ps1 — Carica EPUBs e EDICT sul volume Fly.io
# Eseguire DOPO: fly deploy
# Richiede: flyctl e OpenSSH (già installati su Windows 10/11)

$AppName = "rezero-reader"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EpubPattern = Join-Path $ScriptDir "*.epub"
$EdictPath = Join-Path $ScriptDir "reader_data\edict.db"

Write-Host "=== Re:Zero Reader — Deploy Files su Fly.io ===" -ForegroundColor Cyan
Write-Host ""

# Controlla flyctl
if (-not (Get-Command flyctl -ErrorAction SilentlyContinue) -and -not (Get-Command fly -ErrorAction SilentlyContinue)) {
    Write-Host "ERRORE: flyctl non trovato. Installalo da https://fly.io/docs/flyctl/install/" -ForegroundColor Red
    exit 1
}

$FlyCmd = if (Get-Command flyctl -ErrorAction SilentlyContinue) { "flyctl" } else { "fly" }

# Step 1: Crea directory sul volume
Write-Host "Step 1: Creazione directory sul volume..." -ForegroundColor Yellow
& $FlyCmd ssh console -a $AppName -C "mkdir -p /data/epubs /data/reader_data"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRORE: impossibile connettersi all'app. Assicurati che sia deployata." -ForegroundColor Red
    exit 1
}
Write-Host "OK" -ForegroundColor Green

# Step 2: Avvia proxy SSH in background
Write-Host "`nStep 2: Avvio proxy SSH (porta 2222)..." -ForegroundColor Yellow
$ProxyJob = Start-Job -ScriptBlock { 
    & fly proxy 2222:22 -a "rezero-reader" 2>&1 
}
Start-Sleep -Seconds 3
Write-Host "Proxy avviato (Job ID: $($ProxyJob.Id))" -ForegroundColor Green

# Step 3: Upload EPUBs
$Epubs = Get-ChildItem $EpubPattern
Write-Host "`nStep 3: Upload $($Epubs.Count) EPUBs..." -ForegroundColor Yellow

$i = 0
foreach ($epub in $Epubs) {
    $i++
    $SizeMB = [math]::Round($epub.Length / 1MB, 1)
    Write-Host "  [$i/$($Epubs.Count)] $($epub.Name) ($SizeMB MB)..." -NoNewline
    
    $result = & scp -P 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL `
        "$($epub.FullName)" "root@localhost:/data/epubs/$($epub.Name)" 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
    } else {
        Write-Host " ERRORE: $result" -ForegroundColor Red
    }
}

# Step 4: Upload EDICT
Write-Host "`nStep 4: Upload EDICT database (48 MB)..." -ForegroundColor Yellow
if (Test-Path $EdictPath) {
    $result = & scp -P 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL `
        $EdictPath "root@localhost:/data/reader_data/edict.db" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "EDICT OK" -ForegroundColor Green
    } else {
        Write-Host "EDICT ERRORE: $result" -ForegroundColor Red
    }
} else {
    Write-Host "EDICT non trovato in $EdictPath" -ForegroundColor Red
}

# Step 5: Ferma proxy
Write-Host "`nStep 5: Stop proxy SSH..." -ForegroundColor Yellow
Stop-Job $ProxyJob
Remove-Job $ProxyJob

# Step 6: Verifica
Write-Host "`nStep 6: Verifica file sul volume..." -ForegroundColor Yellow
& $FlyCmd ssh console -a $AppName -C "ls /data/epubs/*.epub 2>/dev/null | wc -l && du -sh /data/"

Write-Host "`n=== COMPLETATO ===" -ForegroundColor Cyan
Write-Host "Apri: https://$AppName.fly.dev" -ForegroundColor Green
