# Builds the PRINTYZ Clicker customer edition and (if Inno Setup is installed) its installer.
# Uses the customer policy in customer\customer_policy.json (edit it in the developer edition:
# "Customer settings" page).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $env:LOCALAPPDATA "PRINTYZ\ClickerV2\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Python environment not found: $py (run 'PRINTYZ Studio.bat' once first)" }
Set-Location $root
Write-Host "1/4 Installing build tools..."
& $py -m pip install -q --disable-pip-version-check pyinstaller
Write-Host "2/4 Packaging the program (several minutes)..."
& $py -m PyInstaller "customer\printyz_customer.spec" --noconfirm --distpath "customer\dist" --workpath "customer\build"
$app = Join-Path $root "customer\dist\PRINTYZ Clicker"
Write-Host "3/4 Adding customer settings..."
Copy-Item "customer\edition.json", "customer\customer_policy.json" $app -Force
$env:PRINTYZ_SMOKE_SHOT = Join-Path $root "customer\dist\smoke.png"
$p = Start-Process -FilePath (Join-Path $app "PRINTYZ Clicker.exe") -PassThru -Wait
Remove-Item Env:\PRINTYZ_SMOKE_SHOT
if (-not (Test-Path (Join-Path $root "customer\dist\smoke.png"))) { throw "Smoke test failed: the packaged program did not start" }
Write-Host "    smoke test OK (customer\dist\smoke.png)"
Write-Host "4/4 Building the installer..."
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc "customer\installer.iss"
    Write-Host "Done: customer\output\  (send this Setup file to the customer)"
} else {
    Write-Host "Inno Setup 6 not found. Install it once:  winget install JRSoftware.InnoSetup  - then run again."
    Write-Host "Meanwhile the ready program folder is: $app"
}
