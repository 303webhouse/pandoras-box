# scripts/package-skill.ps1
# Packages an Olympus committee skill folder into a .skill file for Claude.ai upload.
#
# A .skill file is a ZIP archive with a renamed extension. Claude.ai accepts
# either .zip or .skill. We use .skill for clarity.
#
# IMPORTANT: We do NOT use PowerShell's Compress-Archive because Windows
# PowerShell 5.1 writes ZIP entries with backslash separators, which violates
# the ZIP spec and is rejected by Claude.ai's upload validator with the error
# "Zip file contains path with invalid characters". Instead, we use
# System.IO.Compression.ZipArchive directly so we can control entry names.
#
# Structure: SKILL.md is placed at the ZIP ROOT (not nested under a folder).
# The skill's name comes from the YAML `name:` field in SKILL.md, not from
# the archive's directory structure.
#
# Usage:
#   .\scripts\package-skill.ps1 toro          # Packages skills/toro/ -> dist/skills/toro.skill
#   .\scripts\package-skill.ps1 all           # Packages every subfolder in skills/

param(
    [Parameter(Mandatory=$true)]
    [string]$Target
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

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

    $SkillFile = Join-Path $DistDir "$SkillName.skill"
    if (Test-Path $SkillFile) { Remove-Item $SkillFile -Force }

    # Resolve the skill path so we can compute clean relative entries.
    $SkillRoot = (Resolve-Path $SkillPath).Path.TrimEnd('\','/')
    $Prefix    = $SkillRoot + [System.IO.Path]::DirectorySeparatorChar

    $Zip = [System.IO.Compression.ZipFile]::Open(
        $SkillFile,
        [System.IO.Compression.ZipArchiveMode]::Create
    )
    try {
        $Files = Get-ChildItem -Path $SkillRoot -Recurse -File
        foreach ($File in $Files) {
            # Compute relative path from skill root, normalize to forward slashes.
            $Relative = $File.FullName.Substring($Prefix.Length).Replace('\','/')

            # SKILL.md sits at the ZIP root; references/* and any other content
            # is preserved at its relative path. The wrapping folder (e.g. "toro/")
            # is intentionally stripped so the YAML `name:` field is canonical.
            $Entry = $Zip.CreateEntry(
                $Relative,
                [System.IO.Compression.CompressionLevel]::Optimal
            )
            $Stream = $Entry.Open()
            try {
                $Bytes = [System.IO.File]::ReadAllBytes($File.FullName)
                $Stream.Write($Bytes, 0, $Bytes.Length)
            } finally {
                $Stream.Dispose()
            }
        }
    } finally {
        $Zip.Dispose()
    }

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
