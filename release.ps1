param(
    [ValidateSet("major","minor","patch","build")]
    [string]$Type="patch"
)

$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$ErrorActionPreference = "Stop"

function Require-Command($name){
    if(-not (Get-Command $name -ErrorAction SilentlyContinue)){
        Write-Host ""
        Write-Host "Required command '$name' was not found in PATH." -ForegroundColor Red
        exit 1
    }
}

# Writes UTF-8 without a byte-order mark (Windows PowerShell's "-Encoding UTF8" adds one).
function Write-Utf8NoBom($path, $text){
    [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding $false))
}

function Find-MSBuild {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    $msbuild = $null
    if(Test-Path $vswhere){
        $msbuild = & $vswhere -latest -products * -requires Microsoft.Component.MSBuild -find "MSBuild\**\Bin\MSBuild.exe" | Select-Object -First 1
    }
    if(-not $msbuild){
        $candidates=@(
        "C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe",
        "C:\Program Files\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\MSBuild.exe",
        "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\MSBuild\Current\Bin\MSBuild.exe",
        "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\MSBuild\Current\Bin\MSBuild.exe"
        )
        foreach($c in $candidates){ if(Test-Path $c){$msbuild=$c;break}}
    }
    if(-not $msbuild){ Write-Host "MSBuild.exe not found." -ForegroundColor Red; exit 1}
    return $msbuild
}

function Invoke-Build {
    $msbuild = Find-MSBuild
    $solution = Join-Path $ProjectRoot "build\ygo.sln"

    if (!(Test-Path $solution)) {
        throw "Solution not found: $solution (run premake5 first)"
    }
    Write-Host "Solution    = [$solution]"
    Write-Host "MSBuild     = [$msbuild]"
    $arguments = @(
        $solution
        "/t:Rebuild"
        "/m"
        "/p:Configuration=Release"
    )

    & $msbuild @arguments

    if ($LASTEXITCODE -ne 0) {
        throw "MSBuild failed (ExitCode=$LASTEXITCODE)"
    }
}

if($Type -eq "build"){
    Invoke-Build
    Write-Host ""
    Write-Host "Build finished." -ForegroundColor Green
    exit 0
}

Require-Command git
Require-Command gh

$config = Join-Path $ProjectRoot "gframe\config.h"
if(!(Test-Path $config)){ throw "config.h not found." }
$updateJson = Join-Path $ProjectRoot "updates\update.json"

$content = Get-Content $config -Raw

function Get-VersionValue($Macro){

    $match = [regex]::Match(
        $content,
        "(?m)^#define\s+$Macro\s+(\d+)"
    )

    if(!$match.Success){
        throw "Couldn't find macro '$Macro'"
    }

    return [int]$match.Groups[1].Value

}

$major = Get-VersionValue "EDOPRO_VERSION_MAJOR"
$minor = Get-VersionValue "EDOPRO_VERSION_MINOR"
$patch = Get-VersionValue "EDOPRO_VERSION_PATCH"

switch($Type){
 "major" {$major++; $minor=0; $patch=0}
 "minor" {$minor++; $patch=0}
 "patch" {$patch++}
}

$version="$major.$minor.$patch"

# Versions must only go up: the updater ignores anything not newer than the
# installed version, so a reused or lower number never reaches players.
if(Test-Path $updateJson){
    $published = (Get-Content $updateJson -Raw | ConvertFrom-Json).version
    if([version]$version -le [version]$published){
        throw "Version $version is not newer than the published version $published (updates/update.json)."
    }
}

# A tag is never reused or moved.
git fetch --tags --quiet origin
if(git tag --list $version){
    throw "Tag $version already exists locally. Pick a new version."
}
if(git ls-remote --tags origin "refs/tags/$version"){
    throw "Tag $version already exists on origin. Pick a new version."
}

# Only commit what the release itself changes.
if(git status --porcelain --untracked-files=no){
    throw "Working tree has uncommitted changes. Commit or stash them before releasing."
}

$match = [regex]::Match(
    $content,
    '(?m)^#define\s+EDOPRO_VERSION_CODENAME\s+"([^"]+)"'
)

if(!$match.Success){
    throw "Couldn't find EDOPRO_VERSION_CODENAME."
}

$currentCodename = $match.Groups[1].Value.Trim()

Write-Host ""
Write-Host "Current Codename: $currentCodename"

$codename = Read-Host "Codename (ENTER = keep '$currentCodename')"

if([string]::IsNullOrWhiteSpace($codename)){
    $codename = $currentCodename
}

function Set-Define($text, $macro, $value){

    return [regex]::Replace(
        $text,
        "(?m)^#define\s+$macro\s+.*$",
        "#define $macro $value"
    )

}

Write-Host ""
Write-Host "=====================================" -ForegroundColor Yellow
Write-Host "        MASQPro Release"
Write-Host "=====================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "Version : $version"
Write-Host "Codename: $codename"
Write-Host ""
$confirm = Read-Host "Continue with this release? (Y/N)"
if($confirm.ToUpper() -ne "Y"){
    Write-Host ""
    Write-Host "Release cancelled. Nothing was changed." -ForegroundColor Red
    exit 0
}
Write-Host ""
Write-Host "Starting release..." -ForegroundColor Green
Write-Host ""

# config.h is only modified after confirmation.
$content = Set-Define $content "EDOPRO_VERSION_MAJOR" $major
$content = Set-Define $content "EDOPRO_VERSION_MINOR" $minor
$content = Set-Define $content "EDOPRO_VERSION_PATCH" $patch
$content = Set-Define $content "EDOPRO_VERSION_CODENAME" "`"$codename`""

Write-Utf8NoBom $config $content

try {
    Invoke-Build
} catch {
    git checkout -- $config
    throw
}

$releaseFiles=@("MASQPro.exe","ocgcore.dll")
$temp=Join-Path $env:TEMP "MASQProRelease"

if(Test-Path $temp){ Remove-Item $temp -Recurse -Force }
New-Item -ItemType Directory $temp | Out-Null

foreach($file in $releaseFiles){
 $src=Join-Path "$ProjectRoot\bin\release" $file
 if(!(Test-Path $src)){ throw "$file not found." }
 Copy-Item $src $temp
}

$zip=Join-Path $ProjectRoot "MASQPro.zip"
if(Test-Path $zip){ Remove-Item $zip -Force }
Compress-Archive -Path "$temp\*" -DestinationPath $zip
Remove-Item $temp -Recurse -Force

$md5=(Get-FileHash $zip -Algorithm MD5).Hash.ToLower()

$json=@{
 version=$version
 files=@(@{
   name="MASQPro.zip"
   url="https://github.com/zedja123/MASQPro/releases/download/$version/MASQPro.zip"
   md5=$md5
 })
}

if(!(Test-Path "$ProjectRoot\updates")){ New-Item -ItemType Directory "$ProjectRoot\updates" | Out-Null }
Write-Utf8NoBom $updateJson ($json | ConvertTo-Json -Depth 5)

# The zip is uploaded to the GitHub release, not committed.
git add -- $config $updateJson
git commit -m "Release $version ($codename)"
git tag $version
git push
git push origin $version

$maxAttempts = 10

for ($i = 0; $i -lt $maxAttempts; $i++) {

    if (git ls-remote --tags origin "refs/tags/$version") {
        break
    }

    Start-Sleep 2
}

$title = "MASQPro $version `"$codename`""

Write-Host ""
Write-Host "Creating GitHub Release..."
Write-Host ""

$output = & gh release create `
    $version `
    $zip `
    --repo zedja123/MASQPro `
    --title $title `
    --verify-tag 2>&1

$exitCode = $LASTEXITCODE

Write-Host $output

if ($exitCode -ne 0) {
    throw "GitHub Release creation failed.`n$output"
}

Write-Host ""
Write-Host "Release created successfully." -ForegroundColor Green
