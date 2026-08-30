param(
  [string]$PythonExe = "python",
  [string]$InnoCompiler = "ISCC.exe",
  [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\")).Path
$stageRoot = Join-Path $projectRoot "build\windows\app"
$installerRoot = Join-Path $projectRoot "build\windows\installer"
$specRoot = Join-Path $projectRoot "build\windows\pyinstaller"
$venvRoot = Join-Path $projectRoot "build\windows\build-venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$runtimeRequirements = Join-Path $projectRoot "deploy\windows\requirements-runtime.txt"

New-Item -ItemType Directory -Force -Path $stageRoot, $installerRoot, $specRoot | Out-Null
Get-ChildItem -LiteralPath $stageRoot -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

if (-not (Test-Path -LiteralPath $venvPython)) {
  & $PythonExe -m venv $venvRoot
}
& $venvPython -m pip install --disable-pip-version-check --no-input `
  -r $runtimeRequirements "PyInstaller==6.21.0"

$excludedModules = @(
  "cv2", "funasr", "huggingface_hub", "librosa", "lightning", "matplotlib",
  "mediapipe", "modelscope", "numba", "numpy", "onnxruntime", "pandas",
  "playwright", "pyarrow", "pytorch_lightning", "scipy", "sentence_transformers",
  "sklearn", "sounddevice", "sympy", "tokenizers", "torch", "torchaudio",
  "torchvision", "transformers", "ultralytics", "umap"
)
$excludeArgs = @()
foreach ($module in $excludedModules) {
  $excludeArgs += "--exclude-module"
  $excludeArgs += $module
}

& $venvPython -m PyInstaller --noconfirm --clean --onedir --noconsole `
  --contents-directory "." `
  --name HuTaoAssistant `
  --paths $projectRoot `
  --add-data "$projectRoot\app\static;app\static" `
  --hidden-import app.loop_factory `
  --collect-all webview `
  --collect-all clr_loader `
  --exclude-module tests --exclude-module external --exclude-module model_training `
  @excludeArgs `
  --specpath $specRoot `
  --distpath (Join-Path $specRoot "dist") `
  --workpath (Join-Path $specRoot "work") `
  (Join-Path $projectRoot "scripts\windows\launcher.py")

$builtRoot = Join-Path $specRoot "dist\HuTaoAssistant"
if (-not (Test-Path -LiteralPath $builtRoot)) {
  throw "PyInstaller did not produce $builtRoot"
}
Get-ChildItem -LiteralPath $builtRoot -Force | Copy-Item -Destination $stageRoot -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $stageRoot "data"), (Join-Path $stageRoot "models"), (Join-Path $stageRoot "personas"), (Join-Path $stageRoot "logs") | Out-Null

if (-not $SkipInstaller) {
  & $InnoCompiler (Join-Path $projectRoot "deploy\windows\HutaoAssistant.iss")
  if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE"
  }
  Write-Host "Installer created under $installerRoot"
} else {
  Write-Host "Packaged application created under $stageRoot"
}
