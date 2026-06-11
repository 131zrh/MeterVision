namespace MeterVision.App.Services.Chassis;

public interface IChassisService
{
    bool IsConnected { get; }

    string Mode { get; }

    string? PortName { get; }

    IReadOnlyList<string> GetAvailablePorts();

    ChassisCommandResult Connect(string? portName);

    ChassisCommandResult Disconnect();

    ChassisCommandResult MoveUp(int steps);

    ChassisCommandResult MoveDown(int steps);

    ChassisCommandResult RotateLeft(int steps);

    ChassisCommandResult RotateRight(int steps);

    ChassisCommandResult Stop();

    ChassisCommandResult Home();

    ChassisStatus GetStatus();
}
