using System.IO.Ports;

namespace MeterVision.App.Services.Chassis;

public sealed class MockChassisService : IChassisService
{
    private int _liftSteps;
    private int _rotationSteps;
    private string _lastCommand = "NONE";

    public bool IsConnected { get; private set; }

    public string Mode => "模拟底盘";

    public string? PortName { get; private set; }

    public IReadOnlyList<string> GetAvailablePorts()
    {
        return SerialPort.GetPortNames().OrderBy(name => name).ToArray();
    }

    public ChassisCommandResult Connect(string? portName)
    {
        PortName = string.IsNullOrWhiteSpace(portName) ? "MOCK" : portName;
        IsConnected = true;
        _lastCommand = "CONNECT";

        return ChassisCommandResult.Ok(
            _lastCommand,
            $"已进入模拟连接模式：{PortName}。没有真实 STM32 时，所有命令只记录日志。");
    }

    public ChassisCommandResult Disconnect()
    {
        var disconnectedPort = PortName ?? "MOCK";
        IsConnected = false;
        PortName = null;
        _lastCommand = "DISCONNECT";

        return ChassisCommandResult.Ok(_lastCommand, $"已断开模拟连接：{disconnectedPort}。");
    }

    public ChassisCommandResult MoveUp(int steps)
    {
        _liftSteps += steps;
        return Send($"UP {steps}", $"模拟底盘上升 {steps} 步，当前升降位置：{_liftSteps}。");
    }

    public ChassisCommandResult MoveDown(int steps)
    {
        _liftSteps -= steps;
        return Send($"DOWN {steps}", $"模拟底盘下降 {steps} 步，当前升降位置：{_liftSteps}。");
    }

    public ChassisCommandResult RotateLeft(int steps)
    {
        _rotationSteps -= steps;
        return Send($"ROTATE_LEFT {steps}", $"模拟底盘左转 {steps} 步，当前旋转位置：{_rotationSteps}。");
    }

    public ChassisCommandResult RotateRight(int steps)
    {
        _rotationSteps += steps;
        return Send($"ROTATE_RIGHT {steps}", $"模拟底盘右转 {steps} 步，当前旋转位置：{_rotationSteps}。");
    }

    public ChassisCommandResult Stop()
    {
        return Send("STOP", "模拟急停命令已触发。");
    }

    public ChassisCommandResult Home()
    {
        _liftSteps = 0;
        _rotationSteps = 0;
        return Send("HOME", "模拟底盘已回零，升降位置和旋转位置都归零。");
    }

    public ChassisStatus GetStatus()
    {
        return new ChassisStatus(IsConnected, Mode, PortName, _liftSteps, _rotationSteps, _lastCommand);
    }

    private ChassisCommandResult Send(string command, string message)
    {
        _lastCommand = command;

        if (!IsConnected)
        {
            return ChassisCommandResult.Fail(command, $"未连接底盘，命令未发送：{command}。");
        }

        return ChassisCommandResult.Ok(command, message);
    }
}
