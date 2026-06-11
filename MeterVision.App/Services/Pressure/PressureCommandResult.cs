namespace MeterVision.App.Services.Pressure;

public sealed record PressureCommandResult(
    bool Success,
    string Command,
    string Message,
    double CurrentPressure,
    DateTime Timestamp)
{
    public static PressureCommandResult Ok(string command, string message, double currentPressure)
    {
        return new PressureCommandResult(true, command, message, currentPressure, DateTime.Now);
    }

    public static PressureCommandResult Fail(string command, string message, double currentPressure)
    {
        return new PressureCommandResult(false, command, message, currentPressure, DateTime.Now);
    }
}
