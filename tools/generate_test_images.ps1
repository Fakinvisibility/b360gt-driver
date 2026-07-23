param(
    [string]$OutputDirectory = 'test-images',
    [int]$Width = 320,
    [int]$Height = 480
)

Add-Type -AssemblyName System.Drawing

$fullOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
[System.IO.Directory]::CreateDirectory($fullOutput) | Out-Null

function Save-SolidImage {
    param(
        [string]$Name,
        [System.Drawing.Color]$Color
    )

    $bitmap = New-Object System.Drawing.Bitmap($Width, $Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.Clear($Color)
        $path = Join-Path $fullOutput $Name
        $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
        Write-Output "Generated $path"
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

Save-SolidImage 'black.png' ([System.Drawing.Color]::Black)
Save-SolidImage 'red.png' ([System.Drawing.Color]::Red)
Save-SolidImage 'green.png' ([System.Drawing.Color]::Lime)
Save-SolidImage 'blue.png' ([System.Drawing.Color]::Blue)
Save-SolidImage 'white.png' ([System.Drawing.Color]::White)

$pattern = New-Object System.Drawing.Bitmap($Width, $Height)
$graphics = [System.Drawing.Graphics]::FromImage($pattern)
try {
    $halfWidth = [int]($Width / 2)
    $halfHeight = [int]($Height / 2)
    $graphics.FillRectangle([System.Drawing.Brushes]::Red, 0, 0, $halfWidth, $halfHeight)
    $graphics.FillRectangle([System.Drawing.Brushes]::Lime, $halfWidth, 0, $halfWidth, $halfHeight)
    $graphics.FillRectangle([System.Drawing.Brushes]::Blue, 0, $halfHeight, $halfWidth, $halfHeight)
    $graphics.FillRectangle([System.Drawing.Brushes]::White, $halfWidth, $halfHeight, $halfWidth, $halfHeight)
    $graphics.FillRectangle([System.Drawing.Brushes]::Black, 0, 0, 32, 32)

    $path = Join-Path $fullOutput 'orientation-pattern.png'
    $pattern.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    Write-Output "Generated $path"
}
finally {
    $graphics.Dispose()
    $pattern.Dispose()
}
