namespace MeterVision.App.Services.Pressure;

public interface IPressureService
{
    bool IsConnected { get; }

    string Mode { get; }

    double CurrentPressure { get; }

    PressureCommandResult Connect();

    PressureCommandResult Disconnect();

    PressureCommandResult Increase(double step);

    PressureCommandResult Decrease(double step);

    PressureCommandResult Hold();

    PressureCommandResult Vent();

    PressureCommandResult Stop();

    PressureCommandResult CapturePoint(double targetPressure);
}
