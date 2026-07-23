param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [ValidateSet('RGB', 'BGR')]
    [string]$InputOrder = 'RGB',

    [ValidateSet('Interleaved', 'RowPlanar', 'ColumnLanes3')]
    [string]$Layout = 'Interleaved',

    [int]$Width = 480,
    [int]$Height = 320,
    [int]$Offset = 8,
    [switch]$FlipX,
    [switch]$FlipY
)

Add-Type -AssemblyName System.Drawing

$resolvedInput = (Resolve-Path -LiteralPath $InputPath).Path
$input = [System.IO.File]::ReadAllBytes($resolvedInput)
$pixelBytes = $Width * $Height * 3

if ($Offset -lt 0 -or ($Offset + $pixelBytes) -gt $input.Length) {
    throw "Input does not contain a complete ${Width}x${Height} RGB888 frame at offset $Offset."
}

$bitmap = New-Object System.Drawing.Bitmap(
    $Width,
    $Height,
    [System.Drawing.Imaging.PixelFormat]::Format24bppRgb
)

$rect = New-Object System.Drawing.Rectangle(0, 0, $Width, $Height)
$data = $bitmap.LockBits(
    $rect,
    [System.Drawing.Imaging.ImageLockMode]::WriteOnly,
    [System.Drawing.Imaging.PixelFormat]::Format24bppRgb
)

try {
    $stride = [Math]::Abs($data.Stride)
    $destination = New-Object byte[] ($stride * $Height)

    for ($y = 0; $y -lt $Height; $y++) {
        $sourceY = if ($FlipY) { $Height - 1 - $y } else { $y }

        for ($x = 0; $x -lt $Width; $x++) {
            $sourceX = if ($FlipX) { $Width - 1 - $x } else { $x }
            $target = $y * $stride + $x * 3

            if ($Layout -eq 'ColumnLanes3') {
                if (($Width % 3) -ne 0) {
                    throw 'ColumnLanes3 requires a width divisible by 3.'
                }

                $row = $Offset + ($sourceY * $Width * 3)
                $laneWidth = $Width / 3
                $lane = $sourceX % 3
                $laneX = [Math]::Floor($sourceX / 3)
                $source = $row + ($lane * $laneWidth * 3) + ($laneX * 3)

                if ($InputOrder -eq 'RGB') {
                    $destination[$target] = $input[$source + 2]
                    $destination[$target + 1] = $input[$source + 1]
                    $destination[$target + 2] = $input[$source]
                }
                else {
                    $destination[$target] = $input[$source]
                    $destination[$target + 1] = $input[$source + 1]
                    $destination[$target + 2] = $input[$source + 2]
                }
            }
            elseif ($Layout -eq 'RowPlanar') {
                $row = $Offset + ($sourceY * $Width * 3)
                $plane0 = $input[$row + $sourceX]
                $plane1 = $input[$row + $Width + $sourceX]
                $plane2 = $input[$row + ($Width * 2) + $sourceX]

                if ($InputOrder -eq 'RGB') {
                    $destination[$target] = $plane2
                    $destination[$target + 1] = $plane1
                    $destination[$target + 2] = $plane0
                }
                else {
                    $destination[$target] = $plane0
                    $destination[$target + 1] = $plane1
                    $destination[$target + 2] = $plane2
                }
            }
            else {
                $source = $Offset + (($sourceY * $Width + $sourceX) * 3)

                if ($InputOrder -eq 'RGB') {
                    $destination[$target] = $input[$source + 2]
                    $destination[$target + 1] = $input[$source + 1]
                    $destination[$target + 2] = $input[$source]
                }
                else {
                    $destination[$target] = $input[$source]
                    $destination[$target + 1] = $input[$source + 1]
                    $destination[$target + 2] = $input[$source + 2]
                }
            }
        }
    }

    [System.Runtime.InteropServices.Marshal]::Copy(
        $destination,
        0,
        $data.Scan0,
        $destination.Length
    )
}
finally {
    $bitmap.UnlockBits($data)
}

try {
    $fullOutput = [System.IO.Path]::GetFullPath($OutputPath)
    $parent = [System.IO.Path]::GetDirectoryName($fullOutput)
    if (-not [System.IO.Directory]::Exists($parent)) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    $bitmap.Save($fullOutput, [System.Drawing.Imaging.ImageFormat]::Png)
    Write-Output "Rendered $fullOutput"
}
finally {
    $bitmap.Dispose()
}
