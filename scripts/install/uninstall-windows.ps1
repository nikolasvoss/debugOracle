[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$uninstaller = Join-Path $scriptDirectory "uninstall.py"

if ($env:PYTHON_BIN) {
    & $env:PYTHON_BIN $uninstaller @RemainingArgs
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py $uninstaller @RemainingArgs
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $uninstaller @RemainingArgs
} else {
    Write-Error "Python 3.10 or newer is required. Install Python, then rerun this command."
    exit 1
}

exit $LASTEXITCODE
