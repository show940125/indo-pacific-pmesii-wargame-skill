$ErrorActionPreference = "Stop"

$SkillDir = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$Gemini = (Get-Command gemini.cmd -ErrorAction Stop).Source
$Pwsh = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
if (-not $Pwsh) {
    $Pwsh = "powershell.exe"
}

$Command = @"
Set-Location '$SkillDir'
Write-Host 'Gemini CLI OAuth repair for indo-pacific-pmesii-wargame'
Write-Host '1. If prompted, run /auth and choose Sign in with Google.'
Write-Host '2. After auth, send: Return exactly OK_GEMINI_REPAIR and nothing else.'
Write-Host '3. Confirm it answers, then run /quit.'
& '$Gemini' --skip-trust --debug
"@

Start-Process -FilePath $Pwsh -ArgumentList @("-NoExit", "-Command", $Command) -WorkingDirectory $SkillDir
