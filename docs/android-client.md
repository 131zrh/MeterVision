# MeterVision Android 采集端说明

Android 端第一版定位是“拍照采集端”，不在手机上直接跑 YOLO。它负责：

1. 打开相机实时预览。
2. 拍摄压力表照片。
3. 输入量程、给定压力、允许误差、单位。
4. 上传图片到 Windows 上的 `MeterVision.Api`。
5. 显示识别读数、误差和合格结论。

## 1. 启动 Windows 识别服务

在项目根目录运行：

```powershell
dotnet run --project .\MeterVision.Api\MeterVision.Api.csproj
```

默认监听：

```text
http://0.0.0.0:5080
```

健康检查：

```text
http://localhost:5080/api/health
```

识别接口：

```text
POST http://电脑IP:5080/api/infer
```

字段：

- `image`：图片文件，multipart/form-data
- `fullRange`：仪表量程，例如 `5`
- `targetPressure`：给定压力，例如 `1.0`
- `tolerance`：允许误差，例如 `0.05`
- `unit`：单位，例如 `MPa`

## 2. 打开 Android 工程

用 Android Studio 打开：

```text
MeterVision.Android
```

如果 Android Studio 提示 SDK 路径，选择本机 SDK：

```text
D:\SDK
```

如果提示下载 Gradle/Kotlin/CameraX 依赖，允许它同步下载。

## 3. 服务地址怎么填

### Android 模拟器

模拟器访问电脑 localhost 要使用：

```text
http://10.0.2.2:5080/api/infer
```

这是 Android app 里的默认值。

### 真机

手机和电脑要在同一个 Wi-Fi。先查电脑 IP：

```powershell
ipconfig
```

然后在 app 里填写：

```text
http://电脑IPv4地址:5080/api/infer
```

示例：

```text
http://192.168.1.23:5080/api/infer
```

如果真机访问失败，通常是 Windows 防火墙拦截了 `5080` 端口，需要允许当前网络访问。

## 4. 当前版本范围

已完成：

- CameraX 相机预览
- 拍照保存到缓存
- multipart 图片上传
- 显示服务端返回 JSON 中的读数、误差和结论

暂未完成：

- 手机端离线 YOLO/ONNX/TFLite 识别
- 登录、历史记录、本地数据库
- 结果图回传展示
- Android 直接控制 STM32

下一步建议：

1. 先用模拟器或真机跑通拍照上传。
2. 再在 Windows 端把识别结果图也通过 URL 或 base64 返回给手机。
3. 确认链路稳定后，再评估是否把模型移植到 Android 本地。
