#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ServerAddress,
    [Parameter(Mandatory)] [string] $MachineName,
    [ValidateRange(1,65535)] [int] $Port = 8989
)
$ErrorActionPreference = 'Stop'
if (-not (Get-NetIPAddress -AddressFamily IPv4 -IPAddress $ServerAddress -ErrorAction SilentlyContinue)) {
    throw "Assign the operating network address $ServerAddress to this server before enabling ingress."
}
$route = & podman machine ssh $MachineName ip -4 route get 1.1.1.1
if ($LASTEXITCODE -ne 0 -or ($route -join ' ') -notmatch '\bsrc\s+([\d.]+)') {
    throw "Cannot find the IPv4 address of running machine $MachineName."
}
$guestAddress = $Matches[1]
if (-not (Test-NetConnection $guestAddress -Port $Port -InformationLevel Quiet)) {
    throw "The VM at $guestAddress is not accepting connections on port $Port."
}
$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -eq '0.0.0.0' }
if (-not $listener) {
    & netsh interface portproxy add v4tov4 "listenaddress=$ServerAddress" "listenport=$Port" "connectaddress=$guestAddress" "connectport=$Port"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to configure the Windows port proxy.' }
}
$ruleName = "G2R2-VOC-HTTPS-$Port"
if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $ruleName -DisplayName "G2R2 VOC HTTPS" -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $ServerAddress -LocalPort $Port -Profile Domain,Private | Out-Null
}
Write-Host "HTTPS ingress configured for $ServerAddress on port $Port (VM $guestAddress)."
