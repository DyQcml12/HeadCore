param(
    [string]$PythonEnvironment = "D:\Tool\Progrmming-Tool\anaconda\envs\new",
    [string]$OutputPath = "",
    [Guid]$BasePolicyId = "0283ac0f-fff1-49ae-ada1-8a933130cad6"
)

$ErrorActionPreference = "Stop"
$expectedHash = "A0291CE64FC21AD1743626894F97C2E669BCAC44226CD54897A661A1E5A147D0"
$coreDirectory = Join-Path $PythonEnvironment "Lib\site-packages\pydantic_core"
$candidate = Get-ChildItem -LiteralPath $coreDirectory -Filter "_pydantic_core*.pyd" -File
if ($candidate.Count -ne 1) {
    throw "Expected exactly one pydantic_core native extension in $coreDirectory."
}
$actualHash = (Get-FileHash -LiteralPath $candidate.FullName -Algorithm SHA256).Hash
if ($actualHash -ne $expectedHash) {
    throw "The pydantic_core hash changed. Review the new binary before generating a policy."
}
if (-not $OutputPath) {
    $OutputPath = Join-Path $PSScriptRoot "..\output\wdac\pydantic-core-supplement.xml"
}
$resolvedOutput = [IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($resolvedOutput)) -Force | Out-Null

$rules = New-CIPolicyRule -DriverFilePath $candidate.FullName -Level Hash
New-CIPolicy -FilePath $resolvedOutput -Rules $rules -MultiplePolicyFormat | Out-Null
Set-CIPolicyIdInfo -FilePath $resolvedOutput `
    -PolicyName "HutaoChatCore pydantic_core reviewed hash" `
    -SupplementsBasePolicyID $BasePolicyId | Out-Null

Write-Host "Generated review-only supplemental policy: $resolvedOutput"
Write-Host "Binary: $($candidate.FullName)"
Write-Host "SHA256: $actualHash"
Write-Host "This script does not deploy the policy. Submit the XML to the WDAC administrator for review."
