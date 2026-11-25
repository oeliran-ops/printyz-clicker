# Creates "PRINTYZ Clicker Studio" shortcuts on the Desktop and in the Start menu.
$root = Split-Path -Parent $PSScriptRoot
$icon = Join-Path $root "src\printyz_clicker\assets\printyz.ico"
$target = Join-Path $root "PRINTYZ Studio.bat"
$ws = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))
foreach ($dir in $places) {
    $lnk = $ws.CreateShortcut((Join-Path $dir "PRINTYZ Clicker Studio.lnk"))
    $lnk.TargetPath = $target
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = $icon
    $lnk.WindowStyle = 7          # start the launcher window minimised
    $lnk.Description = "PRINTYZ Clicker Studio"
    $lnk.Save()
    Write-Host "Created: $dir\PRINTYZ Clicker Studio.lnk"
}
