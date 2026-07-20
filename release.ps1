param(
    [ValidateSet("major","minor","patch")]
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

Require-Command git
Require-Command gh

$config = Get-ChildItem -Recurse -Filter config.h | Where-Object {$_.FullName -match "gframe"} | Select-Object -First 1
if(!$config){ throw "config.h not found." }

$content = Get-Content $config.FullName -Raw

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

$content = Set-Define $content "EDOPRO_VERSION_MAJOR" $major
$content = Set-Define $content "EDOPRO_VERSION_MINOR" $minor
$content = Set-Define $content "EDOPRO_VERSION_PATCH" $patch
$content = Set-Define $content "EDOPRO_VERSION_CODENAME" "`"$codename`""

Set-Content $config.FullName $content -Encoding UTF8


# Locate MSBuild
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

$version="$major.$minor.$patch"

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
    Write-Host "Release cancelled." -ForegroundColor Red
    exit 0
}
Write-Host ""
Write-Host "Starting release..." -ForegroundColor Green
Write-Host ""

$solution = Join-Path $ProjectRoot "build\ygo.sln"

if (!(Test-Path $solution)) {
    throw "Solution not found: $solution"
}
Write-Host "ProjectRoot = [$ProjectRoot]"
Write-Host "Solution    = [$solution]"
Write-Host "Exists      = $(Test-Path $solution)"
Write-Host "MSBuild     = [$msbuild]"
$arguments = @(
    $solution
    "/t:Rebuild"
    "/m"
    "/p:Configuration=Release"
)

Write-Host "Arguments:"
$arguments | ForEach-Object { Write-Host "  $_" }

& $msbuild @arguments

if ($LASTEXITCODE -ne 0) {
    throw "MSBuild failed (ExitCode=$LASTEXITCODE)"
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
$json | ConvertTo-Json -Depth 5 | Set-Content "$ProjectRoot\updates\update.json" -Encoding UTF8

git add .
git commit -m "Release $version ($codename)"
git tag $version
git push
git push origin $version

$maxAttempts = 10

for ($i = 0; $i -lt $maxAttempts; $i++) {

    $tagFound = git ls-remote --tags origin | Select-String $version

        if ($tagFound) {
            break
        }

    Start-Sleep 2
}

$title = "MASQPro $version `"$codename`""

Write-Host ""
Write-Host "Creating GitHub Release..."
Write-Host ""

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
