# Cooking Fever Tools

Windows desktop tools for automating and calibrating Cooking Fever workflows.

The app is now GUI-first. Double-click the executable to open the dashboard, manage profiles, calibrate positions, capture template images, run the bot, and review logs.

## Main Features

- Dashboard for starting and stopping the bot.
- JSON restaurant profiles stored in `profiles/`.
- Calibration wizard for click positions, customer order regions, and cook/refill timings.
- Asset manager for capturing, previewing, and testing template images.
- Dry-run mode that logs bot clicks and drags without moving the mouse.
- Action monitor, region selector, screenshot tool, mouse tracker, and todo utility.
- Self-contained Windows publish output.

## Run

Double-click:

```text
CookingFeverTools.exe
```

The dashboard creates these folders beside the executable when needed:

```text
assets/
profiles/
screenshots/
logs/
```

## Recommended Setup

1. Open the dashboard.
2. Create or select a profile.
3. Click `Calibrate` and capture the required screen positions and order regions.
4. Click `Assets` and capture these templates:

```text
burger.png
soda.png
hotdog.png
restart-1.png
restart-2.png
```

5. Use `Test Selected` in the asset manager to confirm each template can be found on screen.
6. Start the bot from the dashboard. Use `Dry Run` first if you want to verify behavior without mouse movement.

## Bot Controls

When the bot is running:

- `p` pauses or resumes.
- `gg` stops.
- Command-line bot launches without `--start` still wait for `s`.

## Development

```powershell
dotnet run --project .\src\CookingFeverTools
dotnet run --project .\src\CookingFeverTools -- help
dotnet run --project .\src\CookingFeverTools -- bot --profile ".\profiles\Burger Shop.json" --start
dotnet run --project .\src\CookingFeverTools -- tracker
dotnet run --project .\src\CookingFeverTools -- region
dotnet run --project .\src\CookingFeverTools -- snap
dotnet run --project .\src\CookingFeverTools -- monitor
dotnet run --project .\src\CookingFeverTools -- todo
```

## Publish

```powershell
dotnet publish .\src\CookingFeverTools\CookingFeverTools.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -o .\dist\CookingFeverTools
Copy-Item .\dist\CookingFeverTools\cooking-fever-tools.exe .\CookingFeverTools.exe -Force
```

`CookingFeverTools.exe` is generated locally and ignored by git. Source changes are kept in the repository; release binaries should be attached to GitHub releases instead of committed.
