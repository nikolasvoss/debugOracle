[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$bootstrap = Join-Path $scriptDirectory "bootstrap.py"

if ($env:PYTHON_BIN) {
    & $env:PYTHON_BIN $bootstrap @RemainingArgs
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py $bootstrap @RemainingArgs
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $bootstrap @RemainingArgs
} else {
    Write-Error "Python 3.12 or newer is required. Install Python, then rerun this command."
    exit 1
}

exit $LASTEXITCODE
