namespace MeterVision.App.Services.Chassis;

public sealed record ChassisCommandResult(
    bool Success,
    string Command,
    string Message,
    DateTime Timestamp)
{
    public static ChassisCommandResult Ok(string command, string message)
    {
        return new ChassisCommandResult(true, command, message, DateTime.Now);
    }

    public static ChassisCommandResult Fail(string command, string message)
    {
        return new ChassisCommandResult(false, command, message, DateTime.Now);
    }
}
