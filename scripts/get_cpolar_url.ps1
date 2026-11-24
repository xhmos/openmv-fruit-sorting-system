param([string]$LogPath, [int]$TimeoutSec = 90, [string]$OutFile)
$loops = [math]::Ceiling($TimeoutSec / 2)
for ($i = 0; $i -lt $loops; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Path $LogPath) {
        $m = Select-String -Path $LogPath -Pattern 'https://[a-z0-9-]+\.(?:[a-z0-9]+\.)?cpolar\.(?:top|cn)' -ErrorAction SilentlyContinue
        if ($m) {
            $u = $m[-1].Matches.Value
            if ($OutFile) { [IO.File]::WriteAllText($OutFile, $u, (New-Object Text.UTF8Encoding($false))) }
            Write-Output $u
            exit 0
        }
    }
}
exit 1