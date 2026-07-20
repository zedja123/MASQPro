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

$currentCodename = [regex]::Match(
    $content,
    '(?m)^#define\s+EDOPRO_VERSION_CODENAME\s+"([^"]+)"'
).Groups[1].Value

if([string]::IsNullOrWhiteSpace($currentCodename)){
    throw "Couldn't read EDOPRO_VERSION_CODENAME."
}

Write-Host ""
Write-Host "Current Codename: $currentCodename"

$codename = Read-Host "Codename (ENTER = keep '$currentCodename')"

if([string]::IsNullOrWhiteSpace($codename)){
    $codename = $currentCodename
}


$content = $content `
-replace '#define EDOPRO_VERSION_MAJOR\s+\d+', "#define EDOPRO_VERSION_MAJOR $major" `
-replace '#define EDOPRO_VERSION_MINOR\s+\d+', "#define EDOPRO_VERSION_MINOR $minor" `
-replace '#define EDOPRO_VERSION_PATCH\s+\d+', "#define EDOPRO_VERSION_PATCH $patch" `
-replace '#define EDOPRO_VERSION_CODENAME\s+".*"', "#define EDOPRO_VERSION_CODENAME `"$codename`""

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

if(!(Test-Path $solution)){
    throw "Couldn't find build\ygo.sln. Did you run premake?"
}

if($LASTEXITCODE -ne 0){ throw "Build failed." }

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

gh release create `
    $version `
    $zip `
    --title "MASQPro $version `"$codename`""

Write-Host "Release $version completed."
