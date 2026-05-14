# scripts/package-skill.ps1
# Packages an Olympus committee skill folder into a .skill file for Claude.ai upload.
#
# A .skill file is a ZIP archive with a renamed extension. Claude.ai accepts
# either .zip or .skill. We use .skill for clarity.
#
# Usage:
#   .\scripts\package-skill.ps1 toro          # Packages skills/toro/ -> dist/skills/toro.skill
#   .\scripts\package-skill.ps1 all           # Packages every subfolder in skills/

param(
    [Parameter(Mandatory=$true)]
    [string]$Target
)

$ErrorActionPreference = "Stop"

# Resolve repo root: this script lives in scripts/, so parent of script dir = repo root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$SkillsDir = Join-Path $RepoRoot "skills"
$DistDir   = Join-Path $RepoRoot "dist\skills"

if (-not (Test-Path $SkillsDir -PathType Container)) {
    Write-Error "Skills directory not found: $SkillsDir"
    exit 1
}

if (-not (Test-Path $DistDir)) {
    New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
}

function Package-Skill {
    param([string]$SkillName)

    $SkillPath = Join-Path $SkillsDir $SkillName

    if (-not (Test-Path $SkillPath -PathType Container)) {
        Write-Warning "Skill folder not found, skipping: $SkillPath"
        return
    }

    $SkillMd = Join-Path $SkillPath "SKILL.md"
    if (-not (Test-Path $SkillMd -PathType Leaf)) {
        Write-Warning "Missing SKILL.md in $SkillPath, skipping"
        return
    }

    $ZipPath   = Join-Path $DistDir "$SkillName.zip"
    $SkillFile = Join-Path $DistDir "$SkillName.skill"

    if (Test-Path $ZipPath)   { Remove-Item $ZipPath -Force }
    if (Test-Path $SkillFile) { Remove-Item $SkillFile -Force }

    Compress-Archive -Path $SkillPath -DestinationPath $ZipPath -Force
    Rename-Item -Path $ZipPath -NewName "$SkillName.skill" -Force

    $Size = [math]::Round((Get-Item $SkillFile).Length / 1KB, 1)
    Write-Host "  Packaged: $SkillFile ($Size KB)"
}

Write-Host "Packaging Olympus skills..."

if ($Target -eq "all") {
    $Skills = Get-ChildItem -Path $SkillsDir -Directory
    if ($Skills.Count -eq 0) {
        Write-Warning "No skill folders found in $SkillsDir"
        exit 0
    }
    foreach ($Skill in $Skills) {
        Package-Skill -SkillName $Skill.Name
    }
} else {
    Package-Skill -SkillName $Target
}

Write-Host "Done."
