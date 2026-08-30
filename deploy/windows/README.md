# Windows first-package layout

This folder describes the first Windows 10/11 package. It does not include
model weights or third-party archives. Those are installed as optional packs
only after their redistribution terms have been confirmed.

## Build inputs

The Inno Setup script expects a staged directory at:

```text
build/windows/app/
```

That directory should contain the packaged executable, the embedded runtime,
the desktop UI, the Python modules used by the cloud-API runtime, and any model
packs explicitly approved for redistribution. `build_installer.ps1` creates a
dedicated build virtual environment from `requirements-runtime.txt`; it does
not package the developer's Conda environment.

## Installed layout

The user chooses the root directory, for example `D:\HuTaoAssistant`:

```text
D:\HuTaoAssistant\
├── HuTaoAssistant.exe
├── app\
├── models\
├── data\
├── personas\
├── logs\
├── backups\
└── unins000.exe
```

`data/` is beside the application and is deliberately not hidden in the C
drive. Updates replace only application files. The updater must preserve
`data/`, `models/`, `personas/`, `logs/`, and user-created tools.

## Build

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\windows\build_installer.ps1 `
  -PythonExe "C:\path\to\python.exe" `
  -InnoCompiler "C:\path\to\ISCC.exe"
```

Use `-SkipInstaller` to build and smoke-test only the application directory.

## Installer prerequisites

- Inno Setup 6 on the build machine.
- A staged `build/windows/app/` directory.
- A signed executable for public release.
- License and redistribution review for every model, voice pack, runtime and
  third-party training framework.

The bundled `languages/ChineseSimplified.isl` is the user-contributed Chinese
translation distributed through the official Inno Setup source repository; its
maintainer and source are recorded in that file header.

The generated installer registers itself with Windows Apps and Features and
creates the standard Inno Setup uninstaller. The Start Menu contains an
explicit uninstall shortcut. The uninstall flow offers application-only removal,
application plus models, or complete local-data removal.

The first package intentionally excludes local ASR, local embedding, camera
YOLO/MediaPipe, GPT-SoVITS training, and model weights. These remain separately
downloadable components because they are large and have independent licenses.
