<#
.SYNOPSIS
  Pull new Supernote Work notes from the cluster's read-only SFTP outbox.

.DESCRIPTION
  Lists the remote `outbox/` tree (recursively), downloads files that are new
  or changed since the last run, and records what it fetched in a state file.
  Uses only the OpenSSH `sftp` that ships with Windows 10/11 — nothing to
  install. Read-only on the server side: it never deletes or modifies remote
  files.

  Run by hand, or from Task Scheduler (example at the bottom). Exit code is
  non-zero if the listing or any download failed (state is only updated for a
  successful download, so the next run retries).

.PARAMETER KeyPath
  Private key for user `worknotes`. Windows' ssh refuses keys other users can
  read; lock it down once with:
    icacls $KeyPath /inheritance:r /grant:r "$($env:USERNAME):R"

.PARAMETER AfterDownload
  Optional scriptblock called with the full local paths of newly downloaded
  files — the hook for filing them into OneNote (not implemented here).
#>
[CmdletBinding()]
param(
    [string]$HostName = '172.21.0.6',
    [string]$User = 'worknotes',
    [string]$KeyPath = (Join-Path $env:USERPROFILE '.ssh\supernote_sftp'),
    [string]$LocalDir = (Join-Path $env:USERPROFILE 'SupernoteWork'),
    [string]$RemoteDir = 'outbox',
    [scriptblock]$AfterDownload
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $KeyPath)) { throw "Key not found: $KeyPath" }
New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null
$StateFile = Join-Path $LocalDir '.pull-state.json'
$KnownHosts = Join-Path $LocalDir '.known_hosts'

# sftp batch files take forward slashes; backslashes are escape characters.
function ConvertTo-SftpPath([string]$p) { return ($p -replace '\\', '/') }

function Invoke-Sftp([string[]]$Commands) {
    $batch = New-TemporaryFile
    try {
        Set-Content -LiteralPath $batch -Value $Commands -Encoding ascii
        $out = & sftp -b $batch `
            -i $KeyPath `
            -o BatchMode=yes `
            -o IdentitiesOnly=yes `
            -o StrictHostKeyChecking=accept-new `
            -o "UserKnownHostsFile=$(ConvertTo-SftpPath $KnownHosts)" `
            -o ConnectTimeout=15 `
            "$User@$HostName" 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "sftp failed (exit $LASTEXITCODE): $($out -join "`n")"
        }
        # Batch mode echoes each command as "sftp> ..."; drop those.
        return $out | Where-Object { $_ -is [string] -and $_ -notmatch '^sftp>' }
    }
    finally { Remove-Item -LiteralPath $batch -Force -ErrorAction SilentlyContinue }
}

# Matches OpenSSH `ls -l` lines, e.g.
#   -rw-r--r--    ? 1000     1000          768 Nov 25 19:15 outbox/shi mtng.html
$LsLine = '^(?<type>[-dl])\S{9}\s+\S+\s+\S+\s+\S+\s+(?<size>\d+)\s+(?<date>\w{3}\s+\d{1,2}\s+(?:\d{2}:\d{2}|\d{4}))\s+(?<name>.+)$'

function Get-RemoteTree([string]$Dir) {
    $files = @()
    foreach ($line in (Invoke-Sftp @("ls -l `"$Dir`""))) {
        if ($line -notmatch $LsLine) { continue }
        $leaf = ($Matches['name'] -split '/')[-1]
        if ($leaf -in '.', '..' -or $leaf.StartsWith('.')) { continue }
        $rel = "$Dir/$leaf"
        if ($Matches['type'] -eq 'd') {
            $files += Get-RemoteTree $rel
        }
        elseif ($Matches['type'] -eq '-') {
            $files += [pscustomobject]@{
                Remote = $rel
                Rel    = $rel.Substring($RemoteDir.Length + 1)
                Sig    = "$($Matches['size'])|$($Matches['date'])"
            }
        }
    }
    return $files
}

$state = @{}
if (Test-Path -LiteralPath $StateFile) {
    (Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json).PSObject.Properties |
        ForEach-Object { $state[$_.Name] = $_.Value }
}

$remote = Get-RemoteTree $RemoteDir
$todo = @($remote | Where-Object { $state[$_.Rel] -ne $_.Sig })

if ($todo.Count -eq 0) { Write-Host 'No new notes.'; return }

$cmds = @()
$downloaded = @()
foreach ($f in $todo) {
    $local = Join-Path $LocalDir ($f.Rel -replace '/', '\')
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $local) | Out-Null
    $cmds += "get `"$($f.Remote)`" `"$(ConvertTo-SftpPath $local)`""
    $downloaded += $local
}
Invoke-Sftp $cmds | Out-Null

foreach ($f in $todo) { $state[$f.Rel] = $f.Sig }
$state | ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding utf8

Write-Host "Downloaded $($todo.Count) file(s) to $LocalDir"
if ($AfterDownload) { & $AfterDownload $downloaded }

<#
Task Scheduler example (every 15 min; ExecutionPolicy may be locked by IT):
  schtasks /Create /SC MINUTE /MO 15 /TN SupernoteWorkPull `
    /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\pull-work-notes.ps1"
#>
