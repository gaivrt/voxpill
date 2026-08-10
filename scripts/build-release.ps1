param(
    [switch]$PortableOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$ProjectText = Get-Content -LiteralPath (Join-Path $ProjectRoot "pyproject.toml") -Raw
$VersionMatch = [regex]::Match($ProjectText, '(?m)^version\s*=\s*"([^"]+)"')
if (-not $VersionMatch.Success) {
    throw "Could not read the project version from pyproject.toml"
}
$Version = $VersionMatch.Groups[1].Value

$Uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
if (-not (Test-Path -LiteralPath $Uv -PathType Leaf)) {
    throw "uv.exe not found at $Uv"
}
foreach ($RequiredFile in @(
    "models\asr\model.int8.onnx",
    "models\asr\tokens.txt",
    "models\punctuation\model.int8.onnx",
    "models\punctuation\tokens.json"
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $RequiredFile) -PathType Leaf)) {
        throw "Missing release asset: $RequiredFile"
    }
}

$env:UV_PROJECT_ENVIRONMENT = ".venv-win"
& $Uv run python tools\generate_icon.py
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }

$StagingRoot = Join-Path $ProjectRoot "build\release-dist"
$WorkRoot = Join-Path $ProjectRoot "build\pyinstaller"
& $Uv run pyinstaller --noconfirm --clean --distpath $StagingRoot --workpath $WorkRoot voicekey.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$BundleDir = Join-Path $StagingRoot "VoxPill"
$ReleaseDir = Join-Path $ProjectRoot "dist\release"
New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.md") -Destination $BundleDir -Force

Add-Type -AssemblyName System.IO.Compression.FileSystem
$PortableZip = Join-Path $ReleaseDir "VoxPill-$Version-portable.zip"
if (Test-Path -LiteralPath $PortableZip) {
    Remove-Item -LiteralPath $PortableZip -Force
}
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $BundleDir,
    $PortableZip,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false
)

$Artifacts = @($PortableZip)
if (-not $PortableOnly) {
    $CompilerCandidates = @(
        $env:INNO_SETUP_COMPILER,
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 7\ISCC.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }
    $Iscc = $CompilerCandidates | Select-Object -First 1
    if (-not $Iscc) {
        throw "Inno Setup compiler not found. Install JRSoftware.InnoSetup, then rerun build-release.bat."
    }
    & $Iscc "/DAppVersion=$Version" "/DBundleDir=$BundleDir" (Join-Path $ProjectRoot "installer\VoxPill.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed" }
    $Artifacts += Join-Path $ReleaseDir "VoxPill-$Version-setup.exe"
}

$HashFile = Join-Path $ReleaseDir "SHA256SUMS.txt"
$HashLines = foreach ($Artifact in $Artifacts) {
    $Hash = Get-FileHash -LiteralPath $Artifact -Algorithm SHA256
    "{0}  {1}" -f $Hash.Hash.ToLowerInvariant(), (Split-Path -Leaf $Artifact)
}
Set-Content -LiteralPath $HashFile -Value $HashLines -Encoding ascii

Write-Host "Release artifacts:"
Get-Item -LiteralPath ($Artifacts + $HashFile) | Select-Object Name, Length, LastWriteTime
