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
# Structure (confirmed against Claude.ai upload validator): the ZIP must
# contain a TOP-LEVEL FOLDER named after the skill, with SKILL.md inside it.
#   toro.skill -> toro/SKILL.md
#                 toro/references/equities.md
#                 toro/references/crypto.md
# A flat layout (SKILL.md at the ZIP root, no wrapping folder) is rejected.
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
    # We anchor entries on the PARENT of the skill folder so the skill folder
    # itself becomes the top-level directory inside the ZIP (toro/SKILL.md).
    $SkillRoot = (Resolve-Path $SkillPath).Path.TrimEnd('\','/')
    $ParentDir = (Split-Path -Parent $SkillRoot).TrimEnd('\','/')
    $Prefix    = $ParentDir + [System.IO.Path]::DirectorySeparatorChar

    $Zip = [System.IO.Compression.ZipFile]::Open(
        $SkillFile,
        [System.IO.Compression.ZipArchiveMode]::Create
    )
    try {
        $Files = Get-ChildItem -Path $SkillRoot -Recurse -File
        foreach ($File in $Files) {
            # Compute path relative to skills/ (the parent), normalize to
            # forward slashes. Result: "toro/SKILL.md", "toro/references/...".
            $Relative = $File.FullName.Substring($Prefix.Length).Replace('\','/')

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
    $Skills = Get-ChildItem -Path $SkillsDir -Directory | Where-Object { -not $_.Name.StartsWith("_") }
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
