# MeterVision 上位机原型学习说明

这是一个 Windows 工控上位机原型项目，用于学习：

- C# WPF 桌面程序开发
- 上位机界面布局和按钮事件
- STM32 升降旋转底盘控制的服务层设计
- 压力控制器页面和模拟压力控制流程
- 检定数据展示、误差计算、合格/不合格判定
- Python 压力表识别算法与 C# 上位机的集成方式
- 无硬件情况下的模拟设备开发模式

当前版本还没有接入真实摄像头、真实 STM32 和真实压力控制器。底盘控制和压力控制都先使用模拟服务；数据展示页面已经可以调用 Python 算法包识别测试图片。

## 1. 当前软件功能

运行后右侧有几个页签：

### 底盘控制

- 扫描 COM 口
- 连接 STM32，当前是模拟连接
- 上升、下降、左转、右转、停止、回零
- 日志区显示将要发送的底盘命令

后续拿到 STM32 后，会把 `MockChassisService` 替换成真实串口服务。

### 压力控制

- 连接模拟压力控制器
- 显示当前压力
- 设置目标压力和步进压力
- 升压、降压、稳压、泄压、停止压力
- 采集压力点

后续拿到压力控制协议后，会把 `MockPressureService` 替换成真实通信服务。

### 数据展示

- 设置量程、单位、允许误差、给定压力
- 生成 `0-5MPa` 标准压力点
- 添加模拟识别记录
- 导入压力表图片并调用 Python 算法
- 显示给定压力、识别读数、误差、允许误差、合格结论

这个页面对应老师说的需求：压力给定值和仪表识别值做对比，计算误差，并判断仪表是否合格。

### 流程控制

- 开始自动对中
- 采集当前画面

当前只是流程入口，后续会串联：压力点控制、图像采集、算法识别、数据记录。

## 2. 项目目录

```text
MeterVision/
  MeterVision.sln
  README-学习说明.md
  docs/
    stm32-chassis-protocol-draft.md
    hardware-handoff-checklist.md
  external/
    infer_repro/
      infer_bridge.py
      requirements.txt
      weights/best.pt
      pressure_reader/
      images/
      outputs/
  MeterVision.App/
    MainWindow.xaml
    MainWindow.xaml.cs
    Models/
      MeasurementRecord.cs
    Services/
      Algorithm/
      Chassis/
      Pressure/
      Workflow/
```

## 3. 运行源码

1. 打开 Visual Studio 2022。
2. 打开解决方案：

```text
E:\E-SoftWare\Codex\MeterVision\MeterVision.sln
```

3. 按 `F5` 运行。
4. 如果看到 `MeterVision 上位机原型` 窗口，说明 C# 项目环境正常。

## 4. 必装开发环境

### Visual Studio 2022 Community

下载地址：

```text
https://visualstudio.microsoft.com/zh-hans/vs/community/
```

安装时勾选：

```text
.NET 桌面开发
```

### .NET SDK 9

下载地址：

```text
https://dotnet.microsoft.com/zh-cn/download/dotnet/9.0
```

如果 Visual Studio 已经带了 .NET 9 SDK，可以不用重复安装。

## 5. Python 算法环境

算法包在：

```text
E:\E-SoftWare\Codex\MeterVision\external\infer_repro
```

当前算法是 Python 工程，不是 C# 库。C# 上位机通过启动 Python 进程调用：

```text
external\infer_repro\infer_bridge.py
```

### Python 版本

建议使用 Python 3.10 及以上。当前本机已验证 Python 3.12 可以使用：

```powershell
py -3.12 --version
```

### 安装依赖

在 PowerShell 中执行：

```powershell
py -3.12 -m pip install -r E:\E-SoftWare\Codex\MeterVision\external\infer_repro\requirements.txt
```

主要依赖包括：

- `ultralytics`
- `opencv-python`
- `numpy`
- `PySide6`
- `rapidocr-onnxruntime`
- `torch`

### 验证依赖

```powershell
py -3.12 -c "import cv2, numpy, ultralytics, PySide6, rapidocr_onnxruntime, torch; print('deps ok')"
```

看到：

```text
deps ok
```

说明依赖可用。

### 验证算法桥接脚本

```powershell
cd E:\E-SoftWare\Codex\MeterVision

py -3.12 .\external\infer_repro\infer_bridge.py `
  --image .\external\infer_repro\images\1.png `
  --range 5 `
  --target 1 `
  --tolerance 0.05 `
  --unit MPa
```

如果成功，会输出类似 JSON：

```json
{
  "success": true,
  "message": "识别成功",
  "reading": 3.39,
  "targetPressure": 1.0,
  "error": 2.39,
  "tolerance": 0.05,
  "passed": false,
  "unit": "MPa"
}
```

结果图会生成在：

```text
E:\E-SoftWare\Codex\MeterVision\external\infer_repro\outputs\bridge
```

## 6. 数据展示页使用方法

1. 运行软件。
2. 打开右侧 `数据展示` 页签。
3. 设置：
   - 量程：例如 `5`
   - 单位：例如 `MPa`
   - 允许误差：例如 `0.05`
   - 给定压力：例如 `1.0`
4. 点击 `生成 0-5MPa 点位`，生成标准压力点。
5. 点击 `添加模拟识别记录`，测试误差计算和表格显示。
6. 点击 `导入图片并调用算法`，选择测试图片，例如：

```text
E:\E-SoftWare\Codex\MeterVision\external\infer_repro\images\1.png
```

7. 软件会调用 Python 算法，识别读数，并把结果写入数据表。

## 7. 代码结构说明

### 界面层

```text
MainWindow.xaml
```

负责界面布局，类似前端 HTML 或 Android XML。页签、按钮、输入框、表格都在这里。

```text
MainWindow.xaml.cs
```

负责按钮事件和界面逻辑。例如点“升压”“导入图片并调用算法”以后执行什么动作。

### 底盘控制

```text
Services/Chassis/IChassisService.cs
Services/Chassis/MockChassisService.cs
```

`IChassisService` 是接口，定义上位机需要哪些底盘能力。  
`MockChassisService` 是模拟实现，没有 STM32 也能演示。

后续真实硬件接入时，可以新增：

```text
SerialChassisService.cs
```

### 压力控制

```text
Services/Pressure/IPressureService.cs
Services/Pressure/MockPressureService.cs
```

当前先模拟升压、降压、稳压、泄压。  
后续根据压力控制器协议新增真实实现。

### 数据展示

```text
Models/MeasurementRecord.cs
```

表示一条检定数据记录，包括：

- 给定压力
- 识别读数
- 误差
- 允许误差
- 合格/不合格
- 数据来源

### 算法集成

```text
Services/Algorithm/IAlgorithmService.cs
Services/Algorithm/PythonAlgorithmService.cs
external/infer_repro/infer_bridge.py
```

`PythonAlgorithmService` 负责从 C# 调用 Python。  
`infer_bridge.py` 负责调用算法包并输出 JSON。

调用链路是：

```text
WPF 按钮
  -> MainWindow.xaml.cs
  -> PythonAlgorithmService
  -> py -3.12 infer_bridge.py
  -> pressure_reader.PressureReader
  -> JSON 结果
  -> 数据展示表格
```

## 8. 当前学习顺序

建议按这个顺序学：

1. 看 `MainWindow.xaml`
   - 理解 WPF 界面怎么写
   - 找到几个页签：底盘控制、压力控制、数据展示、流程控制

2. 看 `MainWindow.xaml.cs`
   - 理解按钮事件
   - 看数据表如何新增记录

3. 看 `MockChassisService.cs`
   - 理解设备模拟模式

4. 看 `MockPressureService.cs`
   - 理解压力控制流程如何先用模拟替代

5. 看 `MeasurementRecord.cs`
   - 理解检定数据模型

6. 看 `PythonAlgorithmService.cs`
   - 理解 C# 如何调用 Python 脚本

7. 看 `infer_bridge.py`
   - 理解 Python 如何调用算法并输出 JSON

## 9. 后续开发方向

拿到硬件后，下一步做：

1. 新增真实串口实现 `SerialChassisService`
2. 点击连接时真实打开 STM32 的 COM 口
3. 点击底盘按钮时真实发送串口命令
4. 接入 USB 摄像头实时画面
5. 把摄像头画面截图送给算法识别
6. 压力控制协议确定后新增真实压力控制服务
7. 按压力点自动升压、稳压、识别、记录、判定
8. 导出 Excel 或 PDF 检定结果

## 10. 常见问题

### 打开源码后 NuGet 还原失败

先确认电脑可以访问 NuGet，或者在 Visual Studio 中右键解决方案，选择“还原 NuGet 包”。

### 点“导入图片并调用算法”失败

优先检查 Python 依赖：

```powershell
py -3.12 -c "import ultralytics; print('ok')"
```

如果失败，重新安装依赖：

```powershell
py -3.12 -m pip install -r E:\E-SoftWare\Codex\MeterVision\external\infer_repro\requirements.txt
```

### 提示找不到 Python

确认 Python Launcher 可用：

```powershell
py -0p
```

如果没有 `py` 命令，需要重新安装 Python，并勾选 `Add Python to PATH` 或安装 Python Launcher。

### 运行时报串口相关错误

当前版本是模拟底盘，不需要真实 STM32。后续接硬件时才需要确认 COM 口、波特率和命令协议。

### 中文显示乱码

请使用 Visual Studio 2022 打开源码。源码文件建议保持 UTF-8 编码。

### pip show 出现 GBK 编码错误

这是 Windows 控制台显示某些包说明时的编码问题，不代表依赖安装失败。只要 `import` 验证通过即可。
