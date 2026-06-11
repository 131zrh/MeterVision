namespace MeterVision.App.Services.Algorithm;

public sealed class AlgorithmInferenceResult
{
    public bool Success { get; init; }

    public string Message { get; init; } = "";

    public string ImagePath { get; init; } = "";

    public string ResultImagePath { get; init; } = "";

    public double? Reading { get; init; }

    public double TargetPressure { get; init; }

    public double? Error { get; init; }

    public double Tolerance { get; init; }

    public bool Passed { get; init; }

    public string Unit { get; init; } = "MPa";
}
