namespace MeterVision.App.Services.Chassis;

public sealed record ChassisStatus(
    bool IsConnected,
    string Mode,
    string? PortName,
    int LiftSteps,
    int RotationSteps,
    string LastCommand);
