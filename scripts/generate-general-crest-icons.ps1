param([string]$FrontendRoot = (Join-Path $PSScriptRoot '..\app\frontend'))

$ErrorActionPreference = 'Stop'
$generalRoot = Join-Path $FrontendRoot 'general'
$crests = Get-ChildItem -LiteralPath (Join-Path $FrontendRoot 'crests') -Filter 'gerb_*.webp' |
    Sort-Object { [int]($_.BaseName -replace '\D', '') }

foreach ($crest in $crests) {
    $number = [int]($crest.BaseName -replace '\D', '')
    foreach ($pose in @('foot', 'mounted')) {
        $base = if ($pose -eq 'foot') { 'gen-01-transparent.png' } else { 'gen-03-transparent.png' }
        $baseData = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $generalRoot $base)))
        $crestData = [Convert]::ToBase64String([IO.File]::ReadAllBytes($crest.FullName))
        $overlay = if ($pose -eq 'foot') {
            '<image href="data:image/webp;base64,{0}" x="535" y="800" width="250" height="250" preserveAspectRatio="xMidYMid meet"/>' -f $crestData
        } else {
            '<image href="data:image/webp;base64,{0}" x="500" y="615" width="230" height="230" preserveAspectRatio="xMidYMid meet"/>' -f $crestData
        }
        $svg = @"
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1536" role="img" aria-label="Генерал с гербом $number">
  <metadata data-crest="$($crest.Name)" data-pose="$pose"/>
  <image href="data:image/png;base64,$baseData" width="1024" height="1536" preserveAspectRatio="xMidYMid meet"/>
  $overlay
</svg>
"@
        $destination = Join-Path $generalRoot ('general-gerb-{0:D2}-{1}.svg' -f $number, $pose)
        [IO.File]::WriteAllText($destination, $svg, [Text.UTF8Encoding]::new($false))
    }
}

Write-Output ("Generated {0} crest-bound general icons in {1}" -f ($crests.Count * 2), $generalRoot)
