using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;

namespace MeterVision.App.Services.Algorithm;

public sealed class PythonAlgorithmService : IAlgorithmService
{
    public AlgorithmInferenceResult InferImage(string imagePath, double fullRange, double targetPressure, double tolerance, string unit)
    {
        var bridgePath = FindBridgeScript();
        if (bridgePath is null)
        {
            return Fail("未找到 Python 算法桥接脚本 external/infer_repro/infer_bridge.py。", imagePath, targetPressure, tolerance, unit);
        }

        try
        {
            var result = RunPython("py", "-3.12 " + BuildArguments(bridgePath, imagePath, fullRange, targetPressure, tolerance, unit), bridgePath)
                ?? RunPython("python", BuildArguments(bridgePath, imagePath, fullRange, targetPressure, tolerance, unit), bridgePath);

            if (result is null)
            {
                return Fail("没有找到可用的 Python。建议安装 Python 3.10+，或确认 py/python 命令可用。", imagePath, targetPressure, tolerance, unit);
            }

            return result;
        }
        catch (Exception ex)
        {
            return Fail($"算法调用失败：{ex.Message}", imagePath, targetPressure, tolerance, unit);
        }
    }

    private static AlgorithmInferenceResult? RunPython(string fileName, string arguments, string bridgePath)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments,
                WorkingDirectory = Path.GetDirectoryName(bridgePath)!,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
                CreateNoWindow = true,
            };

            using var process = Process.Start(startInfo);
            if (process is null)
            {
                return null;
            }

            var stdout = process.StandardOutput.ReadToEnd();
            var stderr = process.StandardError.ReadToEnd();
            process.WaitForExit(120000);

            if (!process.HasExited)
            {
                process.Kill();
                return new AlgorithmInferenceResult { Success = false, Message = "算法调用超时。" };
            }

            if (string.IsNullOrWhiteSpace(stdout))
            {
                return new AlgorithmInferenceResult { Success = false, Message = $"算法没有输出。{stderr}" };
            }

            var jsonStart = stdout.IndexOf('{');
            if (jsonStart > 0)
            {
                stdout = stdout[jsonStart..];
            }

            var result = JsonSerializer.Deserialize<AlgorithmInferenceResult>(
                stdout,
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });

            if (result is null)
            {
                return new AlgorithmInferenceResult { Success = false, Message = $"算法输出解析失败：{stdout}" };
            }

            return result;
        }
        catch (Exception ex)
        {
            if (ex is System.ComponentModel.Win32Exception)
            {
                return null;
            }

            return new AlgorithmInferenceResult { Success = false, Message = $"算法调用失败：{ex.Message}" };
        }
    }

    private static string BuildArguments(string bridgePath, string imagePath, double fullRange, double targetPressure, double tolerance, string unit)
    {
        return string.Join(
            " ",
            Quote(bridgePath),
            "--image",
            Quote(imagePath),
            "--range",
            fullRange.ToString(CultureInfo.InvariantCulture),
            "--target",
            targetPressure.ToString(CultureInfo.InvariantCulture),
            "--tolerance",
            tolerance.ToString(CultureInfo.InvariantCulture),
            "--unit",
            Quote(unit));
    }

    private static string? FindBridgeScript()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);

        while (current is not null)
        {
            var candidate = Path.Combine(current.FullName, "external", "infer_repro", "infer_bridge.py");
            if (File.Exists(candidate))
            {
                return candidate;
            }

            current = current.Parent;
        }

        return null;
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static AlgorithmInferenceResult Fail(string message, string imagePath, double targetPressure, double tolerance, string unit)
    {
        return new AlgorithmInferenceResult
        {
            Success = false,
            Message = message,
            ImagePath = imagePath,
            TargetPressure = targetPressure,
            Tolerance = tolerance,
            Unit = unit,
        };
    }
}
