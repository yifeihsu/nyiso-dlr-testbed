param([string]$OutputDirectory = '')
$ErrorActionPreference = 'Stop'
$latestRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$latestDocument = Join-Path $latestRoot 'NYGRID_2025_LATEST_MODEL_STRUCTURE.docx'
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $latestRoot 'output/nygrid_2025_latest_handoff/document_render' }
[System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
$latestRender = (Resolve-Path -LiteralPath $OutputDirectory).Path
$latestPdf = Join-Path $latestRender 'NYGRID_2025_LATEST_MODEL_STRUCTURE.pdf'
$latestWord = $null
$latestOpened = $null
try {
    $latestWord = New-Object -ComObject Word.Application
    $latestWord.Visible = $false
    $latestWord.DisplayAlerts = 0
    $latestWord.AutomationSecurity = 3
    $latestOpened = $latestWord.Documents.Open($latestDocument, $false, $true, $false)
    $latestOpened.Fields.Update() | Out-Null
    $latestOpened.ExportAsFixedFormat($latestPdf, 17)
    [pscustomobject]@{
        renderer = 'Microsoft Word native PDF export and Poppler rasterization'
        wordVersion = $latestWord.Version
        input = $latestDocument
        inputSHA256 = (Get-FileHash -LiteralPath $latestDocument -Algorithm SHA256).Hash.ToLowerInvariant()
        output = $latestPdf
        readonlyInput = $true
        fallbackReason = 'Canonical render_docx.py failed: LibreOffice soffice.exe was not found on PATH'
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $latestRender 'word_export_receipt.json') -Encoding utf8
} finally {
    if ($null -ne $latestOpened) {
        $latestOpened.Close($false)
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($latestOpened) | Out-Null
    }
    if ($null -ne $latestWord) {
        $latestWord.Quit($false)
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($latestWord) | Out-Null
    }
}
if (-not (Test-Path -LiteralPath $latestPdf)) { throw 'Word did not export the structure PDF.' }
$latestPoppler = (Get-Command pdftoppm.exe -ErrorAction Stop).Source
& $latestPoppler -scale-to 1600 -png $latestPdf (Join-Path $latestRender 'page')
if ($LASTEXITCODE -ne 0) { throw 'Poppler could not rasterize the Word PDF.' }
Get-ChildItem -LiteralPath $latestRender -Filter 'page-*.png' | Select-Object Name, Length
