# 压力表读数识别系统

基于 YOLO + OpenCV 的压力表自动读数，支持 GUI 图片检测、外接摄像头实时监控、算法独立调用。

## 项目目录

```
infer_repro -2/
├── gui_pyside6.py            # 主程序 GUI 入口
├── camera_monitor.py         # 摄像头实时监控窗口
├── camera_worker.py          # 摄像头采集线程（自动重连）
├── infer_cli.py              # 命令行 YOLO 检测可视化
├── batch_eval.py             # 批量评估脚本
├── core_utils.py             # 几何工具函数
├── pressure_reader/          # 算法包（无 GUI 依赖，可独立调用）
│   ├── _pipeline.py          #   PressureReader 编排器
│   ├── _circle.py            #   霍夫圆检测
│   ├── _contours.py          #   轮廓筛选（刻度 / 指针分离）
│   ├── _refine.py            #   刻度点精修
│   ├── _center.py            #   圆心估计（三级回退）
│   ├── _pointer.py           #   指针直线拟合
│   ├── _correction.py        #   几何自洽修正
│   ├── _angle.py             #   角度 / 读数计算
│   ├── _ocr.py               #   OCR 文字分类
│   ├── _visualization.py     #   结果可视化
│   ├── _config.py            #   全部可调参数
│   ├── _models.py            #   数据容器
│   └── _io.py                #   Unicode 安全 I/O
├── tests/                    # 单元测试
├── images/                   # 测试图片
├── weights/                  # 模型权重
├── outputs/                  # 运行输出（自动生成）
├── requirements.txt          # Python 依赖
├── start.bat                 # Windows 一键启动
└── README.md
```

## 环境准备

Python 3.10+ 环境：

```powershell
pip install -r requirements.txt
```

核心依赖：`ultralytics` `opencv-python` `numpy` `PySide6` `rapidocr-onnxruntime`

## 快速启动

### 1. GUI 主窗口（图片检测）

```powershell
python gui_pyside6.py
```

或双击 `start.bat`。

**使用流程：**

1. 点击「导入压力表图片」
2. 输入量程（或点击「自动识别量程」由 OCR 检测）
3. 点击「自动检测读数」
4. 如需修正，点击「手动校准 (点3下)」依次点击 0 刻度、满刻度、指针尖

### 2. 摄像头实时监控（新增）

```powershell
python gui_pyside6.py
# 点击「启动实时监控」→「启动监控」
```

或直接启动监控窗口（需先启动主窗口或独立传参）。

**使用流程：**

1. 打开主窗口，确认量程设置正确
2. 点击「启动实时监控」，弹出监控窗口
3. 点击「启动监控」，摄像头自动打开
4. 对准压力表，系统每 2 秒自动检测一次，右侧大字显示实时读数
5. 可通过「设置」调整检测间隔、量程、摄像头索引

**特性：**
- 大字读数（48pt），适合 3 米外远距离查看
- 断线自动重连（摄像头拔插后自动恢复）
- 长时间运行稳定（每 30 分钟自动释放驱动资源）
- 窗口置顶，监控窗口与主窗口互不阻塞

### 3. 命令行

```powershell
python infer_cli.py --source images
```

### 4. 批量评估

```powershell
python batch_eval.py
```

输出 `outputs/batch_eval.csv`。

## 算法独立调用

无需 GUI，直接调用 `pressure_reader` 包：

```python
import cv2
from pressure_reader import PressureReader
from pressure_reader._io import cv_imread

reader = PressureReader("weights/best.pt")
image = cv_imread("images/1.png")
result = reader.read(image, full_range=25.0, unit="MPa")

print(result.reading)        # 24.56
print(result.pointer_angle)  # 235.1
print(result.range_angle)    # 265.3
```

算法包不依赖 PySide6，可在无 GUI 服务器环境运行。

## 读数计算原理

假设压力表为均匀圆弧刻度。三个关键方向：圆心 → 0 刻度、圆心 → 指针尖、圆心 → 满刻度。

```
θ1 = clockwise_angle(center → zero, center → tip)
θ2 = clockwise_angle(center → zero, center → max)
reading = full_range / θ2 × θ1
```

**自动检测**：zero / max 来自 YOLO 检测框，center 来自霍夫圆或刻度线投票，tip 来自指针直线拟合。

**手动校准**：三点全部由用户点击，圆心为三点外接圆圆心。

## 手动校准

点击「手动校准 (点3下)」，在弹出窗口中依次点击：

1. 0 刻度位置（绿点）
2. 满刻度位置（蓝点）
3. 指针尖端（红点）

程序根据三点计算外接圆圆心和读数，不依赖 YOLO 或指针检测，是自动检测失败时的可靠兜底方案。

建议：尽量点击实际刻度线，指针点击最外侧端点，使用清晰大图。

## 输出文件

| 文件 | 来源 | 说明 |
|------|------|------|
| `outputs/*_result_view.jpg` | 自动检测 | 标注：十字 + 圆 + 指针线 |
| `outputs/*_manual_view.jpg` | 手动校准 | 标注：三点 + 中心连线 |
| `outputs/*_ocr_view.jpg` | OCR | 标注：文字框 |
| `outputs/*_batch_view.jpg` | 批量评估 | 同上 |
| `outputs/camera_*.jpg` | 摄像头监控（需在设置中开启） | 监控截图 |
| `outputs/batch_eval.csv` | 批量评估 | 检测结果汇总 |
| `Result_pressure_pointer_4yolo_pose.txt` | GUI / 监控 | 检测历史日志 |

## 适用范围与限制

**适用**：单指针机械式压力表、起始刻度与满刻度可见、刻度基本均匀、表盘区域清晰。

**不适用**：双指针表、非线性刻度、严重反光/遮挡/倾斜。

## 常见问题

**找不到 `weights/best.pt`** — 确认模型权重文件存在，或通过 `PressureReader("path/to/model.pt")` 指定路径。

**`ModuleNotFoundError`** — 执行 `pip install -r requirements.txt`。

**自动检测偏差大** — 使用「手动校准 (点3下)」替代。

**自动量程识别错误** — 直接修改量程输入框后重新检测。

**中文路径图片读取失败** — 已使用 `numpy + cv2.imdecode` 处理，若仍失败检查文件是否损坏。

**摄像头打开失败** — 检查摄像头索引是否正确（通常 0 为内置摄像头，1 为 USB 外接）。可在监控窗口「设置」中切换索引。

**摄像头断连** — 系统会自动重连，状态栏变红后插回即可恢复。

**长时间运行内存增长** — 已内置每 100 次检测触发 `gc.collect()`，每 30 分钟重启摄像头驱动。
