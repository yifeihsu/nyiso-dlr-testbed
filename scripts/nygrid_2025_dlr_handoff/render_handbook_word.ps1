param(
    [string]$DocumentPath = '',
    [string]$OutputDirectory = ''
)
$ErrorActionPreference = 'Stop'
$handoffRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not $DocumentPath) { $DocumentPath = Join-Path $handoffRoot 'NYGRID_2025_DLR_HANDOFF.docx' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $handoffRoot 'output/nygrid_2025_dlr_handoff/document_render' }
$handoffDocument = (Resolve-Path -LiteralPath $DocumentPath).Path
[System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
$handoffRender = (Resolve-Path -LiteralPath $OutputDirectory).Path
$handoffPdf = Join-Path $handoffRender 'NYGRID_2025_DLR_HANDOFF.pdf'
$handoffWord = $null
$handoffOpened = $null
try {
    $handoffWord = New-Object -ComObject Word.Application
    $handoffWord.Visible = $false
    $handoffWord.DisplayAlerts = 0
    $handoffWord.AutomationSecurity = 3
    $handoffOpened = $handoffWord.Documents.Open($handoffDocument, $false, $true, $false)
    $handoffOpened.Fields.Update() | Out-Null
    $handoffOpened.ExportAsFixedFormat($handoffPdf, 17)
    [pscustomobject]@{
        renderer = 'Microsoft Word installed native PDF export'
        wordVersion = $handoffWord.Version
        input = $handoffDocument
        output = $handoffPdf
        readonlyInput = $true
        fallbackReason = 'Packaged render_docx.py could not find LibreOffice on this Windows host'
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $handoffRender 'word_export_receipt.json') -Encoding utf8
} finally {
    if ($null -ne $handoffOpened) {
        $handoffOpened.Close($false)
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($handoffOpened) | Out-Null
    }
    if ($null -ne $handoffWord) {
        $handoffWord.Quit($false)
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($handoffWord) | Out-Null
    }
}
if (-not (Test-Path -LiteralPath $handoffPdf)) { throw 'Word did not export the handbook PDF.' }
$handoffPoppler = (Get-Command pdftoppm.exe -ErrorAction Stop).Source
& $handoffPoppler -scale-to 1600 -png $handoffPdf (Join-Path $handoffRender 'page')
if ($LASTEXITCODE -ne 0) { throw 'Poppler could not rasterize the Word PDF.' }
Get-ChildItem -LiteralPath $handoffRender -Filter 'page-*.png' | Select-Object Name, Length
