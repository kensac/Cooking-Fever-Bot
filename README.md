# Cooking Fever Tools

C# migration of the original Python screen-automation project for Cooking Fever.

The app is a .NET Windows command-line tool with a few WinForms utilities:

- `bot` runs the Cooking Fever automation bot.
- `tracker` prints live mouse coordinates.
- `region` lets you drag-select screen regions and prints their coordinates.
- `snap` lets you drag-select screen regions and saves PNG screenshots.
- `monitor` opens an action monitor and screenshot tagger.
- `todo` opens the objective/task todo utility from the original project.

## Run

```powershell
dotnet run --project .\src\CookingFeverTools -- help
dotnet run --project .\src\CookingFeverTools -- bot
dotnet run --project .\src\CookingFeverTools -- tracker
dotnet run --project .\src\CookingFeverTools -- region
dotnet run --project .\src\CookingFeverTools -- snap
dotnet run --project .\src\CookingFeverTools -- monitor
dotnet run --project .\src\CookingFeverTools -- todo
```

## Bot Assets

The bot expects template images in `assets/` by default:

- `burger.png`
- `soda.png`
- `hotdog.png`
- `restart-1.png`
- `restart-2.png`

Use `--assets <path>` to point at another folder:

```powershell
dotnet run --project .\src\CookingFeverTools -- bot --assets C:\path\to\templates
```

The source folder I migrated from did not contain those template files, so this repo includes only `assets/.gitkeep`.

## Bot Controls

- `s` starts the bot after launch.
- `p` pauses or resumes.
- `gg` stops.

The bot still uses the original hard-coded screen coordinates and timings, so it expects the game to be positioned and scaled the same way as the Python version.
