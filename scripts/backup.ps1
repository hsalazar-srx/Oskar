# OSKAR — PostgreSQL Backup Script (PRE-7)
# Owner: Manal (Infrastructure Manager)
#
# Schedule via Windows Task Scheduler:
#   Action: PowerShell.exe -NonInteractive -File "C:\Projects\Oskar\scripts\backup.ps1"
#   Trigger: Daily at 02:00
#   Run as: Service account with access to Docker and D:\Backups\
#
# Backup strategy:
#   Daily pg_dump → D:\Backups\oskar\  (30-day local retention)
#   Weekly copy   → NAS via Windows Server Backup (90-day retention)
#   RTO: 4 hours  |  RPO: 24 hours

param(
    [string]$BackupRoot = "D:\Backups\oskar",
    [int]$RetentionDays = 30,
    [string]$ContainerName = "oskar-db",
    [string]$DbName = "oskar",
    [string]$DbUser = "oskar"
)

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupFile = Join-Path $BackupRoot "oskar_${timestamp}.sql.gz"

# Ensure backup directory exists
if (-not (Test-Path $BackupRoot)) {
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    Write-Host "[OSKAR Backup] Created backup directory: $BackupRoot"
}

Write-Host "[OSKAR Backup] Starting pg_dump at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# Run pg_dump inside the PostgreSQL container, pipe through gzip
$dumpCmd = "docker exec $ContainerName pg_dump -U $DbUser -d $DbName --no-password"
$result = Invoke-Expression "$dumpCmd | gzip > `"$backupFile`""

if ($LASTEXITCODE -ne 0) {
    Write-Error "[OSKAR Backup] pg_dump FAILED. Exit code: $LASTEXITCODE"
    # Log to Windows Event Log for monitoring
    Write-EventLog -LogName Application -Source "OSKAR Backup" -EventId 9001 `
        -EntryType Error -Message "OSKAR pg_dump failed at $timestamp"
    exit 1
}

$sizeMB = [math]::Round((Get-Item $backupFile).Length / 1MB, 2)
Write-Host "[OSKAR Backup] Backup written: $backupFile ($sizeMB MB)"

# Log success to Windows Event Log
try {
    Write-EventLog -LogName Application -Source "OSKAR Backup" -EventId 9000 `
        -EntryType Information -Message "OSKAR backup succeeded: $backupFile ($sizeMB MB)"
} catch {
    # Event source may not be registered — log to file instead
    Add-Content -Path (Join-Path $BackupRoot "backup.log") `
        -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') SUCCESS $backupFile ${sizeMB}MB"
}

# Prune backups older than RetentionDays
Write-Host "[OSKAR Backup] Pruning backups older than $RetentionDays days..."
$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem $BackupRoot -Filter "oskar_*.sql.gz" |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    ForEach-Object {
        Remove-Item $_.FullName -Force
        Write-Host "[OSKAR Backup] Pruned: $($_.Name)"
    }

Write-Host "[OSKAR Backup] Completed at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
