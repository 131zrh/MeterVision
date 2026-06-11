namespace MeterVision.App.Models;

public sealed class MeasurementRecord
{
    public int Index { get; init; }

    public double TargetPressure { get; init; }

    public double? Reading { get; init; }

    public double? Error { get; init; }

    public double Tolerance { get; init; }

    public string Unit { get; init; } = "MPa";

    public string Result { get; init; } = "待测";

    public string Source { get; init; } = "模拟";

    public string ImagePath { get; init; } = "";

    public string ResultImagePath { get; init; } = "";

    public DateTime Timestamp { get; init; } = DateTime.Now;

    public string TargetText => $"{TargetPressure:0.###} {Unit}";

    public string ReadingText => Reading.HasValue ? $"{Reading.Value:0.###} {Unit}" : "-";

    public string ErrorText => Error.HasValue ? $"{Error.Value:+0.###;-0.###;0.###} {Unit}" : "-";

    public string ToleranceText => $"±{Tolerance:0.###} {Unit}";

    public string TimestampText => Timestamp.ToString("HH:mm:ss");
}
