[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TargetDirectory
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($TargetDirectory)) {
    $candidates = @(
        $PSScriptRoot
        (Join-Path $PSScriptRoot "..\..\..\.venv\Scripts")
    )
    $TargetDirectory = $candidates |
        Where-Object { Test-Path (Join-Path $_ "b360gt.exe") } |
        Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($TargetDirectory)) {
        throw "Cannot find b360gt.exe beside this script or in the project virtual environment."
    }
}

function Get-NormalizedPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ""
    }
    $expanded = [Environment]::ExpandEnvironmentVariables($Path.Trim())
    try {
        return [IO.Path]::GetFullPath($expanded).TrimEnd("\", "/")
    }
    catch {
        return $expanded.TrimEnd("\", "/")
    }
}

$target = Get-NormalizedPath $TargetDirectory
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$entries = @(
    if (-not [string]::IsNullOrWhiteSpace($userPath)) {
        $userPath -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }
)

$alreadyPresent = $entries | Where-Object {
    (Get-NormalizedPath $_).Equals(
        $target,
        [StringComparison]::OrdinalIgnoreCase
    )
}

if ($alreadyPresent) {
    Write-Host "B360GT is already in the current user's PATH:" -ForegroundColor Yellow
    Write-Host $target
    exit 0
}

$newPath = (@($entries) + $target) -join ";"
if (-not $PSCmdlet.ShouldProcess(
    "current user's PATH",
    "add '$target'"
)) {
    exit 0
}
[Environment]::SetEnvironmentVariable("Path", $newPath, "User")

Write-Host "B360GT was added to the current user's PATH:" -ForegroundColor Green
Write-Host $target
Write-Host ""
Write-Host "Open a new PowerShell window, then run from any directory:"
Write-Host "  b360gt start"
Write-Host "  b360gt status"
Write-Host "  b360gt stop"
