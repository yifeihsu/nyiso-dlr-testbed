param([string]$OutputDirectory = '')
$ErrorActionPreference = 'Stop'
$repairRepo = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
$repairDocument = Join-Path $repairRepo 'output/nygrid_2025_moses_repair/delivery/docs/NYGRID_2025_MOSES_REPAIR_MODEL_STRUCTURE.docx'
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $repairRepo 'output/nygrid_2025_moses_repair/delivery/document_render' }
[System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
$repairRender = (Resolve-Path -LiteralPath $OutputDirectory).Path
$repairPdf = Join-Path $repairRender 'NYGRID_2025_MOSES_REPAIR_MODEL_STRUCTURE.pdf'
$repairWord = $null
$repairOpened = $null
try {
    $repairWord = New-Object -ComObject Word.Application
    $repairWord.Visible = $false
    $repairWord.DisplayAlerts = 0
    $repairWord.AutomationSecurity = 3
    $repairOpened = $repairWord.Documents.Open($repairDocument, $false, $true, $false)
    $repairOpened.Fields.Update() | Out-Null
    $repairOpened.ExportAsFixedFormat($repairPdf, 17)
    [pscustomobject]@{
        renderer = 'Microsoft Word native PDF export and Poppler rasterization'
        wordVersion = $repairWord.Version
        input = $repairDocument
        inputSHA256 = (Get-FileHash -LiteralPath $repairDocument -Algorithm SHA256).Hash.ToLowerInvariant()
        output = $repairPdf
        readonlyInput = $true
        fallbackReason = 'Canonical render_docx.py failed because LibreOffice soffice.exe was not found on PATH'
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $repairRender 'word_export_receipt.json') -Encoding utf8
} finally {
    if ($null -ne $repairOpened) {
        $repairOpened.Close($false)
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($repairOpened) | Out-Null
    }
    if ($null -ne $repairWord) {
        $repairWord.Quit($false)
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($repairWord) | Out-Null
    }
}
if (-not (Test-Path -LiteralPath $repairPdf)) { throw 'Word did not export the structure PDF.' }
$repairPoppler = (Get-Command pdftoppm.exe -ErrorAction Stop).Source
& $repairPoppler -scale-to 1600 -png $repairPdf (Join-Path $repairRender 'page')
if ($LASTEXITCODE -ne 0) { throw 'Poppler could not rasterize the Word PDF.' }
Get-ChildItem -LiteralPath $repairRender -Filter 'page-*.png' | Select-Object Name, Length
