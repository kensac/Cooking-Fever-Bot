using System.Diagnostics;
using System.Text;
using System.Windows.Forms;

namespace CookingFeverTools;

internal sealed class BotProcessController : IDisposable
{
    private Process? _process;

    public event Action<string>? LogReceived;
    public event Action<string>? StateChanged;

    public bool IsRunning => _process is { HasExited: false };

    public void Start(BotLaunchOptions options)
    {
        if (IsRunning)
        {
            throw new InvalidOperationException("The bot is already running.");
        }

        var executable = Environment.ProcessPath ?? Application.ExecutablePath;
        var arguments = BuildArguments(options);
        var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = executable,
                Arguments = arguments,
                WorkingDirectory = AppPaths.AppDirectory,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8
            },
            EnableRaisingEvents = true
        };

        process.OutputDataReceived += (_, eventArgs) =>
        {
            if (eventArgs.Data is not null)
            {
                LogReceived?.Invoke(eventArgs.Data);
            }
        };
        process.ErrorDataReceived += (_, eventArgs) =>
        {
            if (eventArgs.Data is not null)
            {
                LogReceived?.Invoke(eventArgs.Data);
            }
        };
        process.Exited += (_, _) =>
        {
            StateChanged?.Invoke($"Stopped with exit code {process.ExitCode}");
            process.Dispose();
            if (ReferenceEquals(_process, process))
            {
                _process = null;
            }
        };

        if (!process.Start())
        {
            throw new InvalidOperationException("The bot process did not start.");
        }

        _process = process;
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        StateChanged?.Invoke("Running");
    }

    public void Stop()
    {
        if (_process is null)
        {
            return;
        }

        try
        {
            if (!_process.HasExited)
            {
                _process.Kill(entireProcessTree: true);
            }
        }
        catch (InvalidOperationException)
        {
        }
    }

    public void Dispose()
    {
        Stop();
        _process?.Dispose();
    }

    private static string BuildArguments(BotLaunchOptions options)
    {
        var args = new List<string>
        {
            "bot",
            "--profile",
            Quote(options.ProfilePath),
            "--assets",
            Quote(options.AssetsDirectory),
            "--confidence",
            options.Confidence.ToString("0.00", System.Globalization.CultureInfo.InvariantCulture),
            "--delay",
            "0",
            "--start"
        };

        if (options.DryRun)
        {
            args.Add("--dry-run");
        }

        return string.Join(" ", args);
    }

    private static string Quote(string value)
    {
        return $"\"{value.Replace("\"", "\\\"", StringComparison.Ordinal)}\"";
    }
}

internal sealed record BotLaunchOptions(string ProfilePath, string AssetsDirectory, double Confidence, bool DryRun);
