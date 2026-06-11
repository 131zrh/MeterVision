namespace MeterVision.App.Services.Pressure;

public sealed class MockPressureService : IPressureService
{
    public bool IsConnected { get; private set; }

    public string Mode => "模拟压力控制";

    public double CurrentPressure { get; private set; }

    public PressureCommandResult Connect()
    {
        IsConnected = true;
        return PressureCommandResult.Ok("PRESSURE_CONNECT", "已进入模拟压力控制模式。", CurrentPressure);
    }

    public PressureCommandResult Disconnect()
    {
        IsConnected = false;
        return PressureCommandResult.Ok("PRESSURE_DISCONNECT", "已断开模拟压力控制。", CurrentPressure);
    }

    public PressureCommandResult Increase(double step)
    {
        if (!IsConnected)
        {
            return NotConnected("PRESSURE_UP");
        }

        CurrentPressure += Math.Abs(step);
        return PressureCommandResult.Ok("PRESSURE_UP", $"模拟升压 {step:0.###} MPa。", CurrentPressure);
    }

    public PressureCommandResult Decrease(double step)
    {
        if (!IsConnected)
        {
            return NotConnected("PRESSURE_DOWN");
        }

        CurrentPressure = Math.Max(0, CurrentPressure - Math.Abs(step));
        return PressureCommandResult.Ok("PRESSURE_DOWN", $"模拟降压 {step:0.###} MPa。", CurrentPressure);
    }

    public PressureCommandResult Hold()
    {
        if (!IsConnected)
        {
            return NotConnected("PRESSURE_HOLD");
        }

        return PressureCommandResult.Ok("PRESSURE_HOLD", "模拟稳压中。", CurrentPressure);
    }

    public PressureCommandResult Vent()
    {
        if (!IsConnected)
        {
            return NotConnected("PRESSURE_VENT");
        }

        CurrentPressure = 0;
        return PressureCommandResult.Ok("PRESSURE_VENT", "模拟泄压完成，压力归零。", CurrentPressure);
    }

    public PressureCommandResult Stop()
    {
        if (!IsConnected)
        {
            return NotConnected("PRESSURE_STOP");
        }

        return PressureCommandResult.Ok("PRESSURE_STOP", "模拟压力控制停止。", CurrentPressure);
    }

    public PressureCommandResult CapturePoint(double targetPressure)
    {
        if (!IsConnected)
        {
            return NotConnected("PRESSURE_CAPTURE");
        }

        return PressureCommandResult.Ok(
            "PRESSURE_CAPTURE",
            $"模拟采集压力点，目标压力 {targetPressure:0.###} MPa。",
            CurrentPressure);
    }

    private PressureCommandResult NotConnected(string command)
    {
        return PressureCommandResult.Fail(command, "未连接压力控制器，命令未发送。", CurrentPressure);
    }
}
