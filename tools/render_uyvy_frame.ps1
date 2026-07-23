param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [int]$Width = 480,
    [int]$Height = 480,
    [int]$Offset = 8
)

Add-Type -AssemblyName System.Drawing

function Limit-Byte {
    param([int]$Value)
    if ($Value -lt 0) { return [byte]0 }
    if ($Value -gt 255) { return [byte]255 }
    return [byte]$Value
}

$resolvedInput = (Resolve-Path -LiteralPath $InputPath).Path
$input = [System.IO.File]::ReadAllBytes($resolvedInput)
$pixelBytes = $Width * $Height * 2

if (($Width % 2) -ne 0) {
    throw 'UYVY requires an even image width.'
}

if ($Offset -lt 0 -or ($Offset + $pixelBytes) -gt $input.Length) {
    throw "Input does not contain a complete ${Width}x${Height} UYVY frame at offset $Offset."
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
        for ($x = 0; $x -lt $Width; $x += 2) {
            $source = $Offset + (($y * $Width + $x) * 2)
            $u = [int]$input[$source] - 128
            $y0 = [int]$input[$source + 1] - 16
            $v = [int]$input[$source + 2] - 128
            $y1 = [int]$input[$source + 3] - 16

            foreach ($pixel in 0, 1) {
                $luma = if ($pixel -eq 0) { $y0 } else { $y1 }
                if ($luma -lt 0) { $luma = 0 }

                $red = (298 * $luma + 409 * $v + 128) -shr 8
                $green = (298 * $luma - 100 * $u - 208 * $v + 128) -shr 8
                $blue = (298 * $luma + 516 * $u + 128) -shr 8
                $target = $y * $stride + ($x + $pixel) * 3

                # System.Drawing Format24bppRgb stores bytes as B, G, R.
                $destination[$target] = Limit-Byte $blue
                $destination[$target + 1] = Limit-Byte $green
                $destination[$target + 2] = Limit-Byte $red
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
