using System.Diagnostics;
using System.Text;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.UseUrls("http://0.0.0.0:5080");

var app = builder.Build();

app.MapGet("/api/health", () => Results.Ok(new
{
    ok = true,
    service = "MeterVision.Api",
    time = DateTimeOffset.Now,
}));

app.MapPost("/api/infer", async (HttpRequest request) =>
{
    if (!request.HasFormContentType)
    {
        return Results.BadRequest(new { success = false, message = "请使用 multipart/form-data 上传图片。" });
    }

    var form = await request.ReadFormAsync();
    var image = form.Files.GetFile("image");
    if (image is null || image.Length == 0)
    {
        return Results.BadRequest(new { success = false, message = "缺少图片字段 image。" });
    }

    var fullRange = ReadDouble(form["fullRange"], 5);
    var targetPressure = ReadDouble(form["targetPressure"], 1);
    var tolerance = ReadDouble(form["tolerance"], 0.05);
    var unit = string.IsNullOrWhiteSpace(form["unit"]) ? "MPa" : form["unit"].ToString();

    var bridgePath = FindBridgeScript();
    if (bridgePath is null)
    {
        return Results.Ok(new
        {
            success = false,
            message = "未找到 external/infer_repro/infer_bridge.py。",
            reading = (double?)null,
            targetPressure,
            error = (double?)null,
            tolerance,
            passed = false,
            unit,
        });
    }

    var captureDir = Path.Combine(Path.GetDirectoryName(bridgePath)!, "outputs", "api_uploads");
    Directory.CreateDirectory(captureDir);

    var extension = Path.GetExtension(image.FileName);
    if (string.IsNullOrWhiteSpace(extension))
    {
        extension = ".jpg";
    }

    var imagePath = Path.Combine(captureDir, $"android_{DateTime.Now:yyyyMMdd_HHmmss_fff}{extension}");
    await using (var stream = File.Create(imagePath))
    {
        await image.CopyToAsync(stream);
    }

    var result = await RunBridgeAsync(bridgePath, imagePath, fullRange, targetPressure, tolerance, unit);
    return Results.Content(result, "application/json", Encoding.UTF8);
});

app.Run();

static double ReadDouble(string? text, double fallback)
{
    return double.TryParse(text, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var value)
        ? value
        : fallback;
}

static string? FindBridgeScript()
{
    foreach (var startPath in new[] { AppContext.BaseDirectory, Directory.GetCurrentDirectory() })
    {
        var current = new DirectoryInfo(startPath);
        while (current is not null)
        {
            var candidate = Path.Combine(current.FullName, "external", "infer_repro", "infer_bridge.py");
            if (File.Exists(candidate))
            {
                return candidate;
            }

            current = current.Parent;
        }
    }

    return null;
}

static async Task<string> RunBridgeAsync(
    string bridgePath,
    string imagePath,
    double fullRange,
    double targetPressure,
    double tolerance,
    string unit)
{
    var pyResult = await RunPythonAsync("py", new[]
    {
        "-3.12",
        bridgePath,
        "--image",
        imagePath,
        "--range",
        fullRange.ToString(System.Globalization.CultureInfo.InvariantCulture),
        "--target",
        targetPressure.ToString(System.Globalization.CultureInfo.InvariantCulture),
        "--tolerance",
        tolerance.ToString(System.Globalization.CultureInfo.InvariantCulture),
        "--unit",
        unit,
    }, bridgePath);

    if (pyResult is not null)
    {
        return pyResult;
    }

    var pythonResult = await RunPythonAsync("python", new[]
    {
        bridgePath,
        "--image",
        imagePath,
        "--range",
        fullRange.ToString(System.Globalization.CultureInfo.InvariantCulture),
        "--target",
        targetPressure.ToString(System.Globalization.CultureInfo.InvariantCulture),
        "--tolerance",
        tolerance.ToString(System.Globalization.CultureInfo.InvariantCulture),
        "--unit",
        unit,
    }, bridgePath);

    return pythonResult ?? """
        {"success":false,"message":"没有找到可用的 Python。","reading":null,"passed":false}
        """;
}

static async Task<string?> RunPythonAsync(string fileName, IReadOnlyList<string> arguments, string bridgePath)
{
    try
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = fileName,
            WorkingDirectory = Path.GetDirectoryName(bridgePath)!,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            CreateNoWindow = true,
        };

        foreach (var argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        using var process = Process.Start(startInfo);
        if (process is null)
        {
            return null;
        }

        var stdoutTask = process.StandardOutput.ReadToEndAsync();
        var stderrTask = process.StandardError.ReadToEndAsync();
        var exited = await Task.Run(() => process.WaitForExit(120000));

        if (!exited)
        {
            process.Kill();
            return """{"success":false,"message":"算法调用超时。","reading":null,"passed":false}""";
        }

        var stdout = await stdoutTask;
        var stderr = await stderrTask;

        if (string.IsNullOrWhiteSpace(stdout))
        {
            return $$"""{"success":false,"message":"算法没有输出：{{JsonEscape(stderr)}}","reading":null,"passed":false}""";
        }

        var jsonStart = stdout.IndexOf('{');
        if (jsonStart > 0)
        {
            stdout = stdout[jsonStart..];
        }

        return stdout;
    }
    catch (System.ComponentModel.Win32Exception)
    {
        return null;
    }
    catch (Exception ex)
    {
        return $$"""{"success":false,"message":"算法调用失败：{{JsonEscape(ex.Message)}}","reading":null,"passed":false}""";
    }
}

static string JsonEscape(string value)
{
    return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
}
