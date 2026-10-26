$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$appRoot = Join-Path $projectRoot 'agent-app'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$launcherPath = Join-Path $appRoot 'launch.py'
$iconPath = Join-Path $appRoot 'static\brand\aisi-icon.ico'
foreach ($requiredPath in @($pythonPath, $launcherPath, $iconPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) { throw "Missing file: $requiredPath" }
}
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktopPath 'AISI-figure.lnk'
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($shortcutPath)
if ((Test-Path -LiteralPath $shortcutPath) -and $shortcut.TargetPath -ne $pythonPath) {
    throw 'A different shortcut already uses this name. Rename it before trying again.'
}
$shortcut.TargetPath = $pythonPath
$shortcut.Arguments = '"' + $launcherPath + '"'
$shortcut.WorkingDirectory = $appRoot
$shortcut.IconLocation = $iconPath + ',0'
$shortcut.Description = 'AISI-figure - scientific figure editor'
$shortcut.WindowStyle = 1
$shortcut.Save()
$legacyPath = Join-Path $desktopPath 'AISI-lab-figure.lnk'
if (Test-Path -LiteralPath $legacyPath) {
    $legacy = $shortcutShell.CreateShortcut($legacyPath)
    if ($legacy.TargetPath -eq $pythonPath -and $legacy.Arguments -eq $shortcut.Arguments) {
        Remove-Item -LiteralPath $legacyPath
    }
}
Write-Output $shortcutPath
