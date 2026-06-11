namespace MeterVision.App.Services.Algorithm;

public interface IAlgorithmService
{
    AlgorithmInferenceResult InferImage(string imagePath, double fullRange, double targetPressure, double tolerance, string unit);
}
