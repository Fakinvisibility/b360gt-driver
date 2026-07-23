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
$remaining = @(
    $entries | Where-Object {
        -not (Get-NormalizedPath $_).Equals(
            $target,
            [StringComparison]::OrdinalIgnoreCase
        )
    }
)

if ($remaining.Count -eq $entries.Count) {
    Write-Host "B360GT is not in the current user's PATH." -ForegroundColor Yellow
    exit 0
}

if (-not $PSCmdlet.ShouldProcess(
    "current user's PATH",
    "remove '$target'"
)) {
    exit 0
}
[Environment]::SetEnvironmentVariable("Path", ($remaining -join ";"), "User")

Write-Host "B360GT was removed from the current user's PATH:" -ForegroundColor Green
Write-Host $target
Write-Host ""
Write-Host "Open a new PowerShell window to apply the change."
