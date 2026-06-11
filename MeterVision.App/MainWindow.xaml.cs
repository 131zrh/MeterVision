using System.Globalization;
using System.Collections.ObjectModel;
using System.IO;
using System.Windows;
using System.Windows.Threading;
using Microsoft.Win32;
using MeterVision.App.Models;
using MeterVision.App.Services.Algorithm;
using MeterVision.App.Services.Camera;
using MeterVision.App.Services.Chassis;
using MeterVision.App.Services.Pressure;
using MeterVision.App.Services.Workflow;
using OpenCvSharp.WpfExtensions;
using Cv2 = OpenCvSharp.Cv2;
using Mat = OpenCvSharp.Mat;

namespace MeterVision.App;

public partial class MainWindow : Window
{
    private readonly IChassisService _chassisService = new MockChassisService();
    private readonly IPressureService _pressureService = new MockPressureService();
    private readonly IAlgorithmService _algorithmService = new PythonAlgorithmService();
    private readonly IWorkflowService _workflowService = new MockWorkflowService();
    private readonly OpenCvCameraService _cameraService = new();
    private readonly DispatcherTimer _cameraTimer = new();
    private readonly ObservableCollection<MeasurementRecord> _measurementRecords = new();
    private Mat? _latestCameraFrame;

    public MainWindow()
    {
        InitializeComponent();
        MeasurementDataGrid.ItemsSource = _measurementRecords;
        _cameraTimer.Interval = TimeSpan.FromMilliseconds(40);
        _cameraTimer.Tick += CameraTimer_Tick;
        RefreshSerialPorts();
        RefreshConnectionUi();
        RefreshPressureUi();
        RefreshCameraUi();
        AppendLog("软件启动完成。");
        AppendLog("当前使用模拟底盘服务和模拟压力控制服务，没有真实硬件也可以开发和演示流程。");
    }

    protected override void OnClosed(EventArgs e)
    {
        _cameraTimer.Stop();
        _latestCameraFrame?.Dispose();
        _cameraService.Dispose();
        base.OnClosed(e);
    }

    private void RefreshPortsButton_Click(object sender, RoutedEventArgs e)
    {
        RefreshSerialPorts();
    }

    private void ConnectButton_Click(object sender, RoutedEventArgs e)
    {
        ChassisCommandResult result;

        if (!_chassisService.IsConnected)
        {
            var selectedPort = PortComboBox.SelectedItem as string;
            result = _chassisService.Connect(selectedPort);
        }
        else
        {
            result = _chassisService.Disconnect();
        }

        AppendCommandResult(result);
        RefreshConnectionUi();
    }

    private void MoveUpButton_Click(object sender, RoutedEventArgs e)
    {
        AppendCommandResult(_chassisService.MoveUp(1));
    }

    private void MoveDownButton_Click(object sender, RoutedEventArgs e)
    {
        AppendCommandResult(_chassisService.MoveDown(1));
    }

    private void RotateLeftButton_Click(object sender, RoutedEventArgs e)
    {
        AppendCommandResult(_chassisService.RotateLeft(1));
    }

    private void RotateRightButton_Click(object sender, RoutedEventArgs e)
    {
        AppendCommandResult(_chassisService.RotateRight(1));
    }

    private void StopButton_Click(object sender, RoutedEventArgs e)
    {
        AppendCommandResult(_chassisService.Stop());
    }

    private void HomeButton_Click(object sender, RoutedEventArgs e)
    {
        AppendCommandResult(_chassisService.Home());
    }

    private void PressureConnectButton_Click(object sender, RoutedEventArgs e)
    {
        var result = _pressureService.IsConnected
            ? _pressureService.Disconnect()
            : _pressureService.Connect();

        AppendPressureResult(result);
        RefreshPressureUi();
    }

    private void PressureUpButton_Click(object sender, RoutedEventArgs e)
    {
        AppendPressureResult(_pressureService.Increase(ReadPressureStep()));
        RefreshPressureUi();
    }

    private void PressureDownButton_Click(object sender, RoutedEventArgs e)
    {
        AppendPressureResult(_pressureService.Decrease(ReadPressureStep()));
        RefreshPressureUi();
    }

    private void PressureHoldButton_Click(object sender, RoutedEventArgs e)
    {
        AppendPressureResult(_pressureService.Hold());
        RefreshPressureUi();
    }

    private void PressureVentButton_Click(object sender, RoutedEventArgs e)
    {
        AppendPressureResult(_pressureService.Vent());
        RefreshPressureUi();
    }

    private void PressureStopButton_Click(object sender, RoutedEventArgs e)
    {
        AppendPressureResult(_pressureService.Stop());
        RefreshPressureUi();
    }

    private void PressureCaptureButton_Click(object sender, RoutedEventArgs e)
    {
        AppendPressureResult(_pressureService.CapturePoint(ReadTargetPressure()));
        RefreshPressureUi();
    }

    private void AutoCenterButton_Click(object sender, RoutedEventArgs e)
    {
        AppendWorkflowStatus(_workflowService.StartAutoCenter());
    }

    private void CaptureButton_Click(object sender, RoutedEventArgs e)
    {
        AppendWorkflowStatus(_workflowService.CaptureFrame());
        var capturePath = CaptureCurrentCameraFrame();
        if (!string.IsNullOrWhiteSpace(capturePath))
        {
            AppendLog($"CAMERA | 当前画面已保存：{capturePath}");
        }
    }

    private void StartCameraButton_Click(object sender, RoutedEventArgs e)
    {
        var cameraIndex = ReadCameraIndex();
        if (!_cameraService.Start(cameraIndex))
        {
            AppendLog($"WARN | CAMERA | {_cameraService.LastError}");
            RefreshCameraUi();
            return;
        }

        _cameraTimer.Start();
        AppendLog($"CAMERA | 摄像头 {cameraIndex} 已启动。");
        RefreshCameraUi();
    }

    private void StopCameraButton_Click(object sender, RoutedEventArgs e)
    {
        StopCameraPreview("摄像头已停止。");
    }

    private void CaptureAndInferButton_Click(object sender, RoutedEventArgs e)
    {
        var capturePath = CaptureCurrentCameraFrame();
        if (string.IsNullOrWhiteSpace(capturePath))
        {
            return;
        }

        AppendLog($"CAMERA | 当前画面已保存：{capturePath}");
        RunAlgorithmForImage(capturePath, "摄像头识别");
    }

    private void GeneratePressurePointsButton_Click(object sender, RoutedEventArgs e)
    {
        _measurementRecords.Clear();

        var fullRange = ReadDouble(DataFullRangeTextBox.Text, 5);
        var tolerance = ReadDouble(DataToleranceTextBox.Text, 0.05);
        var unit = ReadUnit();

        for (var i = 0; i <= 5; i++)
        {
            _measurementRecords.Add(new MeasurementRecord
            {
                Index = _measurementRecords.Count + 1,
                TargetPressure = i,
                Reading = null,
                Error = null,
                Tolerance = tolerance,
                Unit = unit,
                Result = i <= fullRange ? "待测" : "超量程",
                Source = "标准点",
            });
        }

        AppendLog($"DATA | 已生成 0-{fullRange:0.###}{unit} 数据点。");
    }

    private void AddMockRecordButton_Click(object sender, RoutedEventArgs e)
    {
        var target = ReadDouble(DataTargetTextBox.Text, 1.0);
        var tolerance = ReadDouble(DataToleranceTextBox.Text, 0.05);
        var unit = ReadUnit();
        var reading = target + 0.02;
        AddMeasurementRecord(target, reading, tolerance, unit, "模拟识别", "", "");
    }

    private void RunAlgorithmButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "选择压力表图片",
            Filter = "图片文件|*.jpg;*.jpeg;*.png;*.bmp|所有文件|*.*",
        };

        if (dialog.ShowDialog() != true)
        {
            return;
        }

        RunAlgorithmForImage(dialog.FileName, "算法识别");
    }

    private void ClearRecordsButton_Click(object sender, RoutedEventArgs e)
    {
        _measurementRecords.Clear();
        AppendLog("DATA | 数据表已清空。");
    }

    private void RefreshSerialPorts()
    {
        PortComboBox.Items.Clear();

        var ports = _chassisService.GetAvailablePorts();
        foreach (var portName in ports)
        {
            PortComboBox.Items.Add(portName);
        }

        if (PortComboBox.Items.Count > 0)
        {
            PortComboBox.SelectedIndex = 0;
            AppendLog($"发现 {PortComboBox.Items.Count} 个串口。");
            return;
        }

        AppendLog("没有发现串口。当前仍可点击“连接 STM32”进入模拟模式。");
    }

    private void RefreshConnectionUi()
    {
        var status = _chassisService.GetStatus();

        if (status.IsConnected)
        {
            StatusTextBlock.Text = $"底盘：已连接 {status.Mode}";
            ConnectButton.Content = "断开连接";
            return;
        }

        StatusTextBlock.Text = "底盘：未连接";
        ConnectButton.Content = "连接 STM32";
    }

    private void RefreshPressureUi()
    {
        PressureStatusTextBlock.Text = _pressureService.IsConnected
            ? $"已连接 {_pressureService.Mode}"
            : "未连接压力控制器";

        PressureConnectButton.Content = _pressureService.IsConnected
            ? "断开压力"
            : "连接模拟压力";

        CurrentPressureTextBlock.Text = $"{_pressureService.CurrentPressure:0.000} MPa";
    }

    private void RefreshCameraUi()
    {
        var isRunning = _cameraService.IsRunning;
        CameraStatusTextBlock.Text = isRunning
            ? $"预览中：摄像头 {_cameraService.CameraIndex}"
            : "未启动";
        CameraStatusTextBlock.Foreground = isRunning
            ? System.Windows.Media.Brushes.LightGreen
            : System.Windows.Media.Brushes.Orange;
        StartCameraButton.IsEnabled = !isRunning;
        StopCameraButton.IsEnabled = isRunning;
        CaptureAndInferButton.IsEnabled = isRunning;
        CameraPlaceholderPanel.Visibility = isRunning
            ? Visibility.Collapsed
            : Visibility.Visible;
    }

    private void CameraTimer_Tick(object? sender, EventArgs e)
    {
        using var frame = _cameraService.ReadFrame();
        if (frame is null)
        {
            StopCameraPreview(_cameraService.LastError);
            return;
        }

        _latestCameraFrame?.Dispose();
        _latestCameraFrame = frame.Clone();
        CameraPreviewImage.Source = frame.ToBitmapSource();
    }

    private string CaptureCurrentCameraFrame()
    {
        if (_latestCameraFrame is null || _latestCameraFrame.Empty())
        {
            AppendLog("WARN | CAMERA | 当前没有可采集的摄像头画面，请先启动摄像头。");
            return "";
        }

        var captureDir = Path.Combine(AppContext.BaseDirectory, "captures");
        Directory.CreateDirectory(captureDir);
        var capturePath = Path.Combine(captureDir, $"meter_capture_{DateTime.Now:yyyyMMdd_HHmmss}.jpg");
        Cv2.ImWrite(capturePath, _latestCameraFrame);
        return capturePath;
    }

    private void StopCameraPreview(string message)
    {
        _cameraTimer.Stop();
        _cameraService.Stop();
        CameraPreviewImage.Source = null;
        RefreshCameraUi();
        AppendLog($"CAMERA | {message}");
    }

    private double ReadPressureStep()
    {
        if (double.TryParse(PressureStepTextBox.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var step) && step > 0)
        {
            return step;
        }

        AppendLog("WARN | PRESSURE_STEP | 步进压力格式不正确，已按 0.1 MPa 处理。");
        PressureStepTextBox.Text = "0.1";
        return 0.1;
    }

    private double ReadTargetPressure()
    {
        if (double.TryParse(TargetPressureTextBox.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var target) && target >= 0)
        {
            return target;
        }

        AppendLog("WARN | PRESSURE_TARGET | 目标压力格式不正确，已按 1.0 MPa 处理。");
        TargetPressureTextBox.Text = "1.0";
        return 1.0;
    }

    private int ReadCameraIndex()
    {
        var selectedText = (CameraIndexComboBox.SelectedItem as System.Windows.Controls.ComboBoxItem)?.Content?.ToString()
            ?? CameraIndexComboBox.Text;

        return int.TryParse(selectedText, NumberStyles.Integer, CultureInfo.InvariantCulture, out var cameraIndex) && cameraIndex >= 0
            ? cameraIndex
            : 0;
    }

    private void RunAlgorithmForImage(string imagePath, string source)
    {
        var fullRange = ReadDouble(DataFullRangeTextBox.Text, 5);
        var target = ReadDouble(DataTargetTextBox.Text, 1.0);
        var tolerance = ReadDouble(DataToleranceTextBox.Text, 0.05);
        var unit = ReadUnit();

        AppendLog($"ALGO | 开始调用算法：{imagePath}");
        var result = _algorithmService.InferImage(imagePath, fullRange, target, tolerance, unit);

        if (!result.Success || result.Reading is null)
        {
            AppendLog($"WARN | ALGO | {result.Message}");
            _measurementRecords.Add(new MeasurementRecord
            {
                Index = _measurementRecords.Count + 1,
                TargetPressure = target,
                Reading = null,
                Error = null,
                Tolerance = tolerance,
                Unit = unit,
                Result = "识别失败",
                Source = source,
                ImagePath = imagePath,
                ResultImagePath = result.ResultImagePath,
            });
            return;
        }

        AddMeasurementRecord(target, result.Reading.Value, tolerance, unit, source, imagePath, result.ResultImagePath);
        AppendLog($"ALGO | {result.Message}，结果图：{result.ResultImagePath}");
    }

    private void AddMeasurementRecord(double target, double reading, double tolerance, string unit, string source, string imagePath, string resultImagePath)
    {
        var error = reading - target;
        var passed = Math.Abs(error) <= Math.Abs(tolerance);

        _measurementRecords.Add(new MeasurementRecord
        {
            Index = _measurementRecords.Count + 1,
            TargetPressure = target,
            Reading = reading,
            Error = error,
            Tolerance = tolerance,
            Unit = unit,
            Result = passed ? "合格" : "不合格",
            Source = source,
            ImagePath = imagePath,
            ResultImagePath = resultImagePath,
        });

        AppendLog($"DATA | 给定 {target:0.###}{unit}，读数 {reading:0.###}{unit}，误差 {error:+0.###;-0.###;0.###}{unit}，结论：{(passed ? "合格" : "不合格")}。");
    }

    private static double ReadDouble(string text, double fallback)
    {
        return double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var value)
            ? value
            : fallback;
    }

    private string ReadUnit()
    {
        var unit = DataUnitTextBox.Text.Trim();
        return string.IsNullOrWhiteSpace(unit) ? "MPa" : unit;
    }

    private void AppendCommandResult(ChassisCommandResult result)
    {
        var prefix = result.Success ? "OK" : "WARN";
        AppendLog($"{prefix} | {result.Command} | {result.Message}");
    }

    private void AppendPressureResult(PressureCommandResult result)
    {
        var prefix = result.Success ? "OK" : "WARN";
        AppendLog($"{prefix} | {result.Command} | {result.Message} 当前压力：{result.CurrentPressure:0.000} MPa");
    }

    private void AppendWorkflowStatus(WorkflowStatus status)
    {
        AppendLog($"FLOW | {status.Step} | {status.Message}");
    }

    private void AppendLog(string message)
    {
        LogTextBox.AppendText($"[{DateTime.Now:HH:mm:ss}] {message}{Environment.NewLine}");
        LogTextBox.ScrollToEnd();
    }
}
