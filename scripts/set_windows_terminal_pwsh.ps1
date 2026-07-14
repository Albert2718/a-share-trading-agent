$settings = Join-Path $env:LOCALAPPDATA "Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json"
if (-not (Test-Path -LiteralPath $settings)) {
    throw "Windows Terminal settings.json not found: $settings"
}

$backup = "$settings.bak-$(Get-Date -Format yyyyMMddHHmmss)"
Copy-Item -LiteralPath $settings -Destination $backup

$json = Get-Content -Raw -Encoding UTF8 -LiteralPath $settings | ConvertFrom-Json
$pwshGuid = "{574e775e-4f2a-5b96-ac1e-a2962a402336}"
$profile = $json.profiles.list |
    Where-Object { $_.guid -eq $pwshGuid -or $_.name -eq "PowerShell 7" } |
    Select-Object -First 1

if (-not $profile) {
    $profile = [pscustomobject]@{
        commandline = "pwsh.exe"
        guid = $pwshGuid
        hidden = $false
        name = "PowerShell 7"
        source = "Windows.Terminal.PowershellCore"
    }
    $json.profiles.list += $profile
}

$json.defaultProfile = $pwshGuid
$text = $json | ConvertTo-Json -Depth 100
[System.IO.File]::WriteAllText($settings, $text, [System.Text.UTF8Encoding]::new($false))

Write-Output "backup=$backup"
Write-Output "defaultProfile=$($json.defaultProfile)"
