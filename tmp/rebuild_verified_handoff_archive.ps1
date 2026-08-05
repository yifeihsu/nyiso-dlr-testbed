param(
    [Parameter(Mandatory = $true)][string]$Workspace,
    [Parameter(Mandatory = $true)][string]$Archive,
    [Parameter(Mandatory = $true)][string]$TopFolder
)

$ErrorActionPreference = 'Stop'
$workspacePath = [IO.Path]::GetFullPath($Workspace).TrimEnd('\', '/')
$archivePath = [IO.Path]::GetFullPath($Archive)
$utf8NoBom = [Text.UTF8Encoding]::new($false)
$excludedTopDirectories = @('.git', '.codex', '.agents', 'tmp')
$manifestName = 'PACKAGE_MANIFEST.csv'
$contentRootName = 'PACKAGE_CONTENT_ROOT.sha256'
$manifestPath = Join-Path $workspacePath $manifestName
$contentRootPath = Join-Path $workspacePath $contentRootName
$tempArchivePath = Join-Path $workspacePath ('tmp\' + [IO.Path]::GetFileName($archivePath) + '.new')

if (-not (Test-Path -LiteralPath $workspacePath -PathType Container)) {
    throw "Workspace does not exist: $workspacePath"
}
$resolvedTempParent = (Resolve-Path -LiteralPath (Split-Path -Parent $tempArchivePath)).Path
if (-not $resolvedTempParent.StartsWith($workspacePath, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Temporary archive path is outside the workspace: $tempArchivePath"
}

function Get-RelativePackagePath([IO.FileInfo]$File) {
    return [IO.Path]::GetRelativePath($workspacePath, $File.FullName).Replace('\', '/')
}

function Get-PackageFiles([bool]$IncludeMetadata) {
    $files = [Collections.Generic.List[IO.FileInfo]]::new()
    foreach ($file in Get-ChildItem -LiteralPath $workspacePath -File -Force) {
        $files.Add($file)
    }
    foreach ($directory in Get-ChildItem -LiteralPath $workspacePath -Directory -Force) {
        if ($excludedTopDirectories -contains $directory.Name) {
            continue
        }
        foreach ($file in Get-ChildItem -LiteralPath $directory.FullName -File -Recurse -Force) {
            $files.Add($file)
        }
    }
    if (-not $IncludeMetadata) {
        $files = @(
            $files | Where-Object {
                $_.FullName -ne $manifestPath -and $_.FullName -ne $contentRootPath
            }
        )
    }
    return @($files | Sort-Object { Get-RelativePackagePath $_ })
}

function Get-FileRecord([IO.FileInfo]$File) {
    [pscustomobject][ordered]@{
        relative_path = Get-RelativePackagePath $File
        size_bytes = $File.Length
        last_write_utc = $File.LastWriteTimeUtc.ToString('o')
        sha256 = (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

function Get-TextSha256([string]$Text) {
    $bytes = $utf8NoBom.GetBytes($Text)
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
}

$payloadRecords = @(Get-PackageFiles $false | ForEach-Object { Get-FileRecord $_ })
$recordStream = (($payloadRecords | ForEach-Object {
    $_.sha256 + '  ' + $_.relative_path
}) -join "`n") + "`n"
$contentRootHash = Get-TextSha256 $recordStream
$contentRootText = @(
    "content_root_sha256=$contentRootHash"
    'algorithm=SHA-256'
    "payload_file_count=$($payloadRecords.Count)"
    'scope=all packaged project payload files except PACKAGE_MANIFEST.csv and PACKAGE_CONTENT_ROOT.sha256'
    'ordering=PACKAGE_MANIFEST.csv row order excluding PACKAGE_CONTENT_ROOT.sha256'
    'path_normalization=package-relative path with forward slash separators; case preserved'
    'record_hash=lowercase hexadecimal SHA-256'
    'record_separator=two ASCII spaces'
    'record_terminator=LF'
    'record_stream_encoding=UTF-8 without BOM'
    'trailing_lf=true'
    'archive_hash_location=sibling .zip.sha256.txt file'
) -join "`n"
[IO.File]::WriteAllText($contentRootPath, $contentRootText + "`n", $utf8NoBom)

$manifestRecords = @(
    $payloadRecords
    Get-FileRecord ([IO.FileInfo]::new($contentRootPath))
) | Sort-Object relative_path
$manifestText = (($manifestRecords | ConvertTo-Csv -NoTypeInformation) -join "`r`n") + "`r`n"
[IO.File]::WriteAllText($manifestPath, $manifestText, $utf8NoBom)

if (Test-Path -LiteralPath $tempArchivePath) {
    Remove-Item -LiteralPath $tempArchivePath -Force
}
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archiveFiles = @(Get-PackageFiles $true)
$fileStream = [IO.File]::Open($tempArchivePath, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite)
try {
    $zip = [IO.Compression.ZipArchive]::new(
        $fileStream, [IO.Compression.ZipArchiveMode]::Create, $false)
    try {
        foreach ($file in $archiveFiles) {
            $relativePath = Get-RelativePackagePath $file
            $entry = $zip.CreateEntry(
                "$TopFolder/$relativePath", [IO.Compression.CompressionLevel]::Optimal)
            $entry.LastWriteTime = $file.LastWriteTime
            $source = $file.OpenRead()
            $target = $entry.Open()
            try {
                $source.CopyTo($target)
            }
            finally {
                $target.Dispose()
                $source.Dispose()
            }
        }
    }
    finally {
        $zip.Dispose()
    }
}
finally {
    $fileStream.Dispose()
}

$manifestRows = @(Import-Csv -LiteralPath $manifestPath)
$expectedEntries = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($row in $manifestRows) {
    [void]$expectedEntries.Add("$TopFolder/$($row.relative_path)")
}
[void]$expectedEntries.Add("$TopFolder/$manifestName")

$verifyStream = [IO.File]::OpenRead($tempArchivePath)
try {
    $zip = [IO.Compression.ZipArchive]::new(
        $verifyStream, [IO.Compression.ZipArchiveMode]::Read, $false)
    try {
        $fileEntries = @($zip.Entries | Where-Object { $_.Name -ne '' })
        if ($fileEntries.Count -ne $expectedEntries.Count) {
            throw "Archive file count mismatch: $($fileEntries.Count) versus $($expectedEntries.Count)."
        }
        foreach ($entry in $fileEntries) {
            if (-not $expectedEntries.Contains($entry.FullName)) {
                throw "Unexpected archive entry: $($entry.FullName)"
            }
        }
        foreach ($row in $manifestRows) {
            $entryName = "$TopFolder/$($row.relative_path)"
            $entry = $zip.GetEntry($entryName)
            if ($null -eq $entry) {
                throw "Missing archive entry: $entryName"
            }
            if ($entry.Length -ne [long]$row.size_bytes) {
                throw "Archive size mismatch: $entryName"
            }
            $stream = $entry.Open()
            try {
                $hasher = [Security.Cryptography.SHA256]::Create()
                try {
                    $entryHash = [Convert]::ToHexString($hasher.ComputeHash($stream)).ToLowerInvariant()
                }
                finally {
                    $hasher.Dispose()
                }
            }
            finally {
                $stream.Dispose()
            }
            if ($entryHash -ne $row.sha256) {
                throw "Archive SHA-256 mismatch: $entryName"
            }
        }
    }
    finally {
        $zip.Dispose()
    }
}
finally {
    $verifyStream.Dispose()
}

$rootRows = @($manifestRows | Where-Object { $_.relative_path -ne $contentRootName })
$verifyRecordStream = (($rootRows | ForEach-Object {
    $_.sha256 + '  ' + $_.relative_path
}) -join "`n") + "`n"
$verifiedContentRoot = Get-TextSha256 $verifyRecordStream
if ($verifiedContentRoot -ne $contentRootHash) {
    throw "Content-root verification mismatch: $verifiedContentRoot versus $contentRootHash."
}
if (-not ($manifestRows.relative_path | Where-Object { $_ -like 'PERFORM/*' })) {
    throw 'PERFORM dataset is missing from the handoff manifest.'
}
if (-not ($manifestRows.relative_path | Where-Object { $_ -like 'ENLITEN-Grid-Econ-Data-main/*' })) {
    throw 'ENLITEN dataset is missing from the handoff manifest.'
}

$tempArchiveHash = (Get-FileHash -LiteralPath $tempArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::Copy($tempArchivePath, $archivePath, $true)
$finalArchiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($finalArchiveHash -ne $tempArchiveHash) {
    throw 'Final archive differs from the verified temporary archive.'
}
$sidecarPath = $archivePath + '.sha256.txt'
$sidecarText = "$finalArchiveHash  $([IO.Path]::GetFileName($archivePath))`n"
[IO.File]::WriteAllText($sidecarPath, $sidecarText, $utf8NoBom)
Remove-Item -LiteralPath $tempArchivePath -Force

[pscustomobject]@{
    archive = $archivePath
    archive_sha256 = $finalArchiveHash
    archive_size_bytes = ([IO.FileInfo]::new($archivePath)).Length
    content_root_sha256 = $contentRootHash
    payload_file_count = $payloadRecords.Count
    manifest_entry_count = $manifestRows.Count
    archive_file_count = $expectedEntries.Count
    sidecar = $sidecarPath
} | Format-List
