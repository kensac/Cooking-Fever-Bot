# Agent Instructions

This repository is a GUI-first Windows desktop app for Cooking Fever tools.

## Version Management

- Keep `version.md` current whenever functionality, packaging, or user-facing behavior changes.
- Keep `src/CookingFeverTools/CookingFeverTools.csproj` `<Version>` in sync with `version.md`.
- Use semantic versions:
  - Patch for fixes and small usability changes.
  - Minor for new features.
  - Major for breaking changes or large workflow changes.
- Add a short note in `version.md` explaining what changed.

## Executable Output

- When the version is updated, build a fresh self-contained Windows executable and place it in the repository root as `CookingFeverTools.exe`.
- Use:

```powershell
dotnet publish .\src\CookingFeverTools\CookingFeverTools.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -o .\dist\CookingFeverTools
Copy-Item .\dist\CookingFeverTools\cooking-fever-tools.exe .\CookingFeverTools.exe -Force
Remove-Item .\dist -Recurse -Force
```

- `CookingFeverTools.exe`, `dist/`, `profiles/`, `logs/`, and `screenshots/` are local generated output and should stay ignored by git.
- After copying the root executable, remove `dist/` unless it is needed for troubleshooting.
- Do not commit generated binaries unless the user explicitly asks for binaries in the repository.

## Verification

- Before handing off, run:

```powershell
dotnet build .\src\CookingFeverTools\CookingFeverTools.csproj -c Release
dotnet format .\src\CookingFeverTools\CookingFeverTools.csproj --verify-no-changes
```

- After publishing, verify that `.\CookingFeverTools.exe` exists in the root directory.
- For GUI changes, smoke test that `.\CookingFeverTools.exe` starts and closes cleanly.
