# 代码结构说明

本文档说明 `infer_repro -2` 项目的主要文件、核心类函数、运行链路和扩展位置。若只想运行程序，请先阅读 `README.md`。

---

## 1. 总体架构

项目可以分为四层：

```text
入口层
├── gui_pyside6.py      # 推荐 GUI，功能最完整
├── gui_pyqt5.py        # 备用 GUI，保留旧版流程
└── infer_cli.py        # 命令行 YOLO 检测可视化

算法层
├── YOLO 起始/结束刻度检测
├── OpenCV 表盘圆、刻度线、指针检测
├── 手动三点校准
└── RapidOCR 表盘文字识别

工具层
└── core_utils.py       # 角度、距离、统计工具

资源与输出
├── weights/best.pt     # YOLO 权重
├── images/             # 图片资源
├── outputs/            # 中间结果和可视化输出
└── Result_pressure_pointer_4yolo_pose.txt
```

推荐主流程在 `gui_pyside6.py` 中完成。它将图片导入、自动量程识别、OCR、自动读数、手动校准和日志记录整合到一个窗口中。

---

## 2. `core_utils.py`

该文件不依赖 Qt，主要保存几何和统计工具，供 CLI 与 GUI 复用。

### `Functions.GetClockAngle(v1, v2)`

计算两个二维向量的顺时针夹角，返回范围约为 `0~360` 度。

实现思路：

- 使用点积计算夹角大小；
- 使用叉积符号判断方向；
- 如果方向为逆侧，则返回 `360 - θ`。

该函数是压力读数换算的核心基础。

### `Functions.Distances(a, b)`

计算两点之间的欧氏距离，并转为整数。

主要用于：

- 判断轮廓到圆心的距离；
- 判断直线段长度；
- 判断指针线段哪一端更远离圆心。

### `Functions.couputeMean(deg)`

使用箱线图思想剔除异常值后求均值。

主要用于刻度线轮廓面积的过滤，减少异常轮廓对均值的影响。

> 函数名保留了原项目中的拼写 `couputeMean`，代码调用处也沿用该名称。

---

## 3. `infer_cli.py`

这是最小命令行入口，只做 YOLO 推理和检测框保存，不做压力读数计算。

### 主要常量

- `BASE_DIR`：当前脚本所在目录；
- `DEFAULT_WEIGHTS`：默认权重 `weights/best.pt`；
- `DEFAULT_OUTPUT`：默认输出目录 `outputs/`。

### `parse_args()`

解析命令行参数：

| 参数 | 作用 |
| --- | --- |
| `--source` | 图片文件或图片目录，必填 |
| `--weights` | YOLO 权重路径，默认 `weights/best.pt` |
| `--conf` | 检测置信度，默认 `0.6` |
| `--project` | 输出根目录，默认 `outputs/` |
| `--name` | 本次输出子目录，默认 `cli_predict` |

### `main()`

执行流程：

1. 检查权重是否存在；
2. 检查输入图片或目录是否存在；
3. 加载 `YOLO(model=..., task='detect')`；
4. 调用模型推理并保存结果图；
5. 打印每张图片的检测框数量和保存目录。

适合用于快速验证权重是否能正常推理。

---

## 4. `gui_pyside6.py`

这是当前推荐维护的主程序。

### 4.1 全局常量

| 常量 | 说明 |
| --- | --- |
| `BASE_DIR` | 当前文件所在目录 |
| `WEIGHT_PATH` | `weights/best.pt` |
| `OUTPUT_DIR` | `outputs/` |
| `RESULT_TXT` | `Result_pressure_pointer_4yolo_pose.txt` |

### 4.2 Unicode 安全图像读写

#### `cv_imread(path)`

使用 `np.fromfile + cv2.imdecode` 读取图片，避免 Windows 下 `cv2.imread` 对中文路径支持不稳定的问题。

#### `cv_imwrite(path, img)`

使用 `cv2.imencode + tofile` 保存图片，避免 `cv2.imwrite` 在中文路径下失败。

PySide6 主流程中的图片读写优先使用这两个函数。

---

## 5. `ManualCalibDialog`

`ManualCalibDialog(QDialog)` 是手动三点校准窗口。

### 功能定位

当自动检测失败或读数偏差较大时，用户可以手动点击：

1. 0 刻度；
2. 满刻度；
3. 指针尖。

程序根据这 3 个点计算圆心和读数。

### 核心属性

| 属性 | 说明 |
| --- | --- |
| `image_bgr` | 原始 BGR 图片 |
| `full_range` | 当前满量程 |
| `clicks` | 用户已点击的原图坐标 |
| `scale` | 显示图到原图的缩放比例 |
| `result_value` | 最终读数 |
| `result_theta` | 指针角度 |
| `result_theta2` | 量程角度 |
| `result_center` | 三点外接圆圆心 |

### `_on_click(event)`

捕获鼠标点击，将显示坐标换算回原图坐标，追加到 `clicks`。

点击未满 3 个点时更新提示文字；点击满 3 个点后调用 `_compute_and_finish()`。

### `_redraw()`

在弹窗图片上绘制已点击点：

- 绿色：0 刻度；
- 蓝色：满刻度；
- 红色：指针尖。

### `_reset()`

清空点击记录，恢复初始图片和提示。

### `_compute_and_finish()`

执行手动校准计算：

1. 根据 3 点外接圆公式计算圆心；
2. 如果 3 点近似共线，则退化为 0 刻度与满刻度中点；
3. 构造 `center → zero`、`center → tip`、`center → max` 三个方向；
4. 调用 `Functions.GetClockAngle` 得到 `θ1` 与 `θ2`；
5. 计算 `reading = full_range / θ2 * θ1`；
6. 保存结果并关闭对话框。

---

## 6. `ImageDetection`

`ImageDetection(QWidget)` 是 PySide6 主窗口类。

### 6.1 初始化与状态

`__init__()` 中主要初始化：

- 图片路径与图片对象；
- YOLO 权重路径；
- 输出目录与日志路径；
- 表盘圆、中心点、指针端点、起止刻度等检测状态；
- 当前量程和单位；
- OCR 引擎与 OCR 结果缓存；
- UI 样式和界面布局。

程序启动时会确保 `outputs/` 存在。

### 6.2 UI 构建方法

| 方法 | 说明 |
| --- | --- |
| `_setup_styles()` | 设置全局 Qt 样式表 |
| `_init_ui()` | 创建窗口标题、三列布局和状态栏 |
| `_build_left_panel()` | 左侧图像输入、量程输入、导入和手动校准按钮 |
| `_build_mid_panel()` | 中间结果图、确认和修改读数按钮 |
| `_build_right_panel()` | 右侧检测信息、OCR 结果、历史日志 |

### 6.3 通用辅助方法

#### `_set_status(msg, is_err=False)`

更新底部状态栏。错误状态使用红色背景，正常状态使用绿色背景。

#### `_get_range()`

读取并校验左侧量程输入框。输入必须是大于 0 的数字。

#### `_refresh_log()`

读取日志文件并显示到右侧历史记录框。读取时使用 `errors='replace'`，可容忍历史日志中存在非 UTF-8 字符。

#### `_apply_range_unit(rng, unit)`

统一更新量程和单位：

- 更新内部 `pressure_range` 和 `pressure_unit`；
- 更新量程输入框；
- 更新量程标签；
- 更新右侧当前量程显示。

---

## 7. PySide6 交互入口

### 7.1 `load_image()`

图片导入入口。

执行流程：

1. 弹出文件选择框；
2. 使用 `cv_imread` 读取图片；
3. 对非 ASCII 文件名生成安全的输出文件名前缀；
4. 在左侧显示缩略图；
5. 自动执行：
   - `auto_detect_range()`；
   - `recognize_text()`；
   - `read_value()`。

每一步都用 `try/except` 包裹，防止某一步失败导致整个界面不可用。

### 7.2 `manual_calibrate()`

手动校准入口。

执行流程：

1. 检查是否已导入图片；
2. 获取当前量程；
3. 打开 `ManualCalibDialog`；
4. 接收读数、角度和圆心结果；
5. 更新右侧读数面板；
6. 写入日志；
7. 绘制手动校准可视化图到 `outputs/*_manual_view.jpg`；
8. 在中间面板显示可视化图。

### 7.3 `confirm()`

向日志中追加 `The reading is correct.`，表示当前读数已确认。

### 7.4 `modify_reading()`

弹出输入框，让用户输入修正读数，并将修正记录追加到日志。

### 7.5 `clear_log()`

清空日志文件和右侧历史记录显示。

---

## 8. 自动量程识别

### `auto_detect_range()`

目标：自动判断压力表满量程和单位。

执行流程：

1. 使用 YOLO 检测起止刻度；
2. 按 `x` 坐标排序，取最右侧检测框中心作为结束刻度位置；
3. 调用 OCR 识别表盘文字；
4. 从 OCR 文本中提取单位，如 `MPa/kPa/Pa/psi/bar/℃` 等；
5. 从 OCR 文本中提取纯数字候选；
6. 如果 YOLO 结束刻度存在，则选择离结束刻度最近的数字作为量程；
7. 如果 YOLO 失败，则选择 OCR 识别出的最大数字作为量程；
8. 调用 `_apply_range_unit()` 更新界面。

YOLO 检测会按 `0.6 → 0.3 → 0.15` 的置信度顺序尝试。

注意：如果 OCR 把刻度数字、精度等级或其他标识误判为量程，用户可以直接手动修改量程输入框。

---

## 9. OCR 表盘文字识别

### 9.1 `OCR_FIELDS`

固定输出五个字段：

```text
仪器名称 / 品牌商标 / 生产厂家 / 压力单位 / 精度等级
```

### 9.2 `_ensure_ocr_engine()`

懒加载 OCR 引擎：

```python
from rapidocr_onnxruntime import RapidOCR
```

首次识别时初始化，后续复用 `self.ocr_engine`。

如果依赖缺失，会提示安装：

```powershell
pip install rapidocr-onnxruntime
```

### 9.3 `_crop_dial_roi()`

决定 OCR 的识别区域：

- 如果之前已经检测到表盘圆 `self.cirleData`，则裁剪表盘圆附近矩形区域；
- 否则返回整张图片。

返回值为：

```text
(roi_image, (offset_x, offset_y))
```

后续绘制 OCR 框时需要把 ROI 坐标加回偏移量。

### 9.4 `_classify_ocr_text(text)`

规则式文本分类器，将 OCR 文本归到五个字段之一。

判断顺序：

1. 压力或温度单位；
2. 精度等级；
3. 生产厂家；
4. 仪器名称；
5. 品牌商标。

部分规则示例：

- 单位：`MPa`、`kPa`、`psi`、`bar`、`mmHg`、`℃`；
- 精度等级：`1.6级`、`(1.5)`、裸小数 `0.05~4.0`；
- 厂家：包含 `公司`、`厂`、`集团`、`Ltd`、`MFG` 等；
- 仪器名：包含 `压力表`、`真空表`、`GAUGE`、`PRESSURE` 等；
- 品牌：短中文、英文品牌或中英混合短串。

纯整数通常视为刻度数字，会返回 `None`。

### 9.5 `recognize_text()`

OCR 主入口。

执行流程：

1. 检查图片；
2. 懒加载 OCR 引擎；
3. 获取 ROI；
4. 调用 RapidOCR；
5. 过滤低置信度文本；
6. 调用 `_classify_ocr_text()` 归类；
7. 每个字段保留置信度最高的一条；
8. 更新右侧 OCR 文本框；
9. 写入日志；
10. 绘制 OCR 可视化图到 `outputs/*_ocr_view.jpg`。

可视化颜色：

- 绿色框：已归类字段；
- 灰色框：未归类 OCR 文本。

---

## 10. 自动读数检测

### 10.1 `_img_cut_circle()`

目标：检测表盘圆并生成表盘区域图。

流程：

1. 对原图做 `pyrMeanShiftFiltering`；
2. 转灰度图；
3. 使用 `cv2.HoughCircles` 检测圆；
4. 如果成功，保存 `self.cirleData = [r, cx, cy]`；
5. 使用圆形 mask 得到 `self.panMask`；
6. 保存 `*_1_imgCutCircle.jpg`；
7. 如果失败，则 `self.cirleData = None`，后续启用 fallback。

### 10.2 `_contours_filter()`

目标：从表盘图中筛选刻度短线和指针候选区域。

流程：

1. 高斯模糊；
2. 灰度化；
3. 自适应阈值；
4. `findContours` 提取轮廓；
5. 根据轮廓到圆心的距离、长宽比、面积筛选刻度线；
6. 根据尺寸筛选可能的指针轮廓；
7. 生成：
   - `self.new_cntset`：刻度短线轮廓；
   - `self.poniterMask`：指针掩码；
   - `self.numLineMask`：刻度掩码；
   - `self.r`：刻度线平均半径。

> 变量名 `poniterMask` 沿用原项目拼写。

### 10.3 `_scale_line_vote_center()`

霍夫圆失败时的圆心 fallback。

流程：

1. 对每条刻度短线轮廓使用 `cv2.fitLine` 拟合直线；
2. 将直线转为 `y = kx + b`；
3. 对直线两两求交点；
4. 过滤图像外交点；
5. 使用 IQR 思路剔除离群交点；
6. 返回平均交点作为圆心。

如果刻度线数量不足或交点过少，返回 `None`。

### 10.4 `_fit_pointer_line()`

目标：从指针掩码中拟合指针线段并确定指针尖端。

流程：

1. 对 `self.poniterMask` 做形态学闭运算；
2. 使用 `cv2.HoughLinesP` 检测直线段；
3. 选择最长线段作为指针候选；
4. 比较线段两端到圆心的距离；
5. 取距离圆心更远的一端作为 `self.farPoint`。

如果未检测到线段，则 `self.farPoint = None`。

### 10.5 `read_value()`

自动读数主流程。

完整流程：

1. 检查图片和量程；
2. 加载 YOLO 权重；
3. 用置信度 `0.6 → 0.3 → 0.15` 依次尝试检测；
4. 取检测框按 `x` 坐标排序后的最左与最右框；
5. 使用两个框中心作为 `zeroPoint` 与 `endPoint`；
6. 调用 `_img_cut_circle()`；
7. 调用 `_contours_filter()`；
8. 决定圆心：
   - 优先使用霍夫圆圆心；
   - 失败则使用 `_scale_line_vote_center()`；
   - 再失败则使用图像几何中心；
9. 调用 `_fit_pointer_line()` 得到指针尖端；
10. 尝试几何自洽中心修正；
11. 计算指针角度 `θ1` 和量程角度 `θ2`；
12. 计算 `reading = rng / θ2 * θ1`；
13. 更新界面；
14. 写入日志；
15. 绘制 `outputs/*_result_view.jpg`。

### 10.6 几何自洽中心修正

在 `read_value()` 中，初步圆心确定后还会尝试修正中心。

修正思想：

- 0 刻度与满刻度构成一条弦；
- 圆心应位于该弦的中垂线上；
- 指针尖端与圆心应位于指针轴线上；
- 两条线的交点可作为新的圆心候选。

如果霍夫圆存在，且新圆心相对旧圆心偏移不超过 `0.3 * 半径`，则采用新圆心。这样可以降低起止刻度框中心和圆检测误差带来的系统偏差。

---

## 11. 读数公式

无论自动检测还是手动校准，最终都使用同一类角度比例公式。

```text
v_zero = zeroPoint - centerPoint
v_tip  = farPoint  - centerPoint
v_max  = endPoint  - centerPoint

θ1 = GetClockAngle(v_zero, v_tip)
θ2 = GetClockAngle(v_zero, v_max)
reading = full_range / θ2 * θ1
```

自动检测时：

- `zeroPoint` 来自 YOLO 最左框中心；
- `endPoint` 来自 YOLO 最右框中心；
- `centerPoint` 来自霍夫圆、刻度线投票或图像中心；
- `farPoint` 来自指针直线拟合。

手动校准时：

- `zeroPoint`、`endPoint`、`farPoint` 来自用户点击；
- `centerPoint` 来自三点外接圆圆心。

---

## 12. `gui_pyqt5.py`

这是备用 GUI，主要保留原项目的传统流程。

特点：

- 使用 PyQt5；
- 需要用户导入图片后点击开始检测；
- 默认满量程由顶部常量 `FULL_RANGE = 10.0` 决定；
- 没有自动量程识别；
- 没有 OCR 识别；
- 没有手动三点校准；
- 输出日志为 `Result_pressure_pointer.txt`。

主要方法与旧流程对应：

| 方法 | 说明 |
| --- | --- |
| `loadImage()` | 导入图片 |
| `ImgCutCircle()` | 霍夫圆检测表盘 |
| `ContoursFilter()` | 轮廓筛选刻度与指针 |
| `FitNumLine()` | 拟合刻度线 |
| `getIntersectionPoints()` | 通过刻度线交点估计圆心 |
| `FitPointerLine()` | 拟合指针线 |
| `Readvalue()` | YOLO + OpenCV 自动读数主流程 |

该文件适合对照旧版本逻辑，不建议作为主要扩展入口。

---

## 13. `start.bat`

Windows 一键启动脚本。

执行策略：

1. 切换到脚本所在目录；
2. 优先使用固定 conda 环境：`C:\Users\DELL\.conda\envs\yolov11\pythonw.exe`；
3. 如果 conda 环境不存在，则查找系统 PATH 中的 `python`；
4. 启动 `gui_pyside6.py`；
5. 如果没有找到 Python，则输出安装提示并暂停窗口。

如果双击没有看到界面，建议在 PowerShell 中手动运行：

```powershell
python gui_pyside6.py
```

---

## 14. 输出与日志

### 14.1 `outputs/`

常见输出：

| 文件 | 来源 | 说明 |
| --- | --- | --- |
| `*_1_imgCutCircle.jpg` | `_img_cut_circle()` | 表盘圆 mask 结果 |
| `*_3_poniterMask.jpg` | `_contours_filter()` | 指针掩码 |
| `*_result_view.jpg` | `read_value()` | 自动读数可视化 |
| `*_manual_view.jpg` | `manual_calibrate()` | 手动校准可视化 |
| `*_ocr_view.jpg` | `recognize_text()` | OCR 可视化 |
| `cli_predict/` | `infer_cli.py` | 命令行 YOLO 可视化 |

### 14.2 日志文件

PySide6 版日志：

```text
Result_pressure_pointer_4yolo_pose.txt
```

日志记录内容包括：

- 自动检测结果；
- 手动校准结果；
- OCR 字段结果；
- 用户确认记录；
- 用户修正读数记录。

---

## 15. 常见扩展位置

### 更换 YOLO 权重

替换：

```text
weights/best.pt
```

如果仍然是检测起始刻度与结束刻度，通常不需要改代码。

### 调整 YOLO 置信度

在 `gui_pyside6.py` 中搜索：

```text
for conf_try in (0.6, 0.3, 0.15)
```

可根据数据集质量调整阈值。

### 调整霍夫圆检测

修改 `_img_cut_circle()` 中：

- `param1`；
- `param2`；
- `minRadius`；
- `maxRadius`。

`param2` 越小越容易检测到圆，但误检也可能增加。

### 调整指针检测

修改 `_fit_pointer_line()` 中：

- 形态学核大小；
- `HoughLinesP` 的阈值；
- `minLineLength`；
- `maxLineGap`。

### 调整 OCR 分类规则

修改 `_classify_ocr_text(text)`。

常见扩展：

- 增加品牌关键字；
- 增加仪器名称同义词；
- 增加厂家后缀；
- 放宽或收紧精度等级判断；
- 调整纯中文短串是否归为品牌。

### 改变读数公式

自动读数公式在 `read_value()` 中：

```text
reading = round((rng / theta2) * theta, 2)
```

手动校准公式在 `ManualCalibDialog._compute_and_finish()` 中：

```text
reading = round((self.full_range / theta2) * theta, 2)
```

如果要支持非线性刻度，需要在这里替换为新的刻度映射逻辑。

### 扩展实时摄像头

当前项目没有保留实时摄像头线程。如果需要实时视频流，可新增摄像头采集线程，然后复用 `read_value()` 中的图像检测逻辑，但需要将文件路径依赖改为直接处理当前帧。

---

## 16. 已知技术限制

- 自动读数依赖起始刻度、结束刻度和指针都能被稳定定位；
- 霍夫圆对强反光、遮挡、椭圆透视较敏感；
- 指针与刻度、文字或阴影粘连时，指针线拟合可能失败；
- OCR 对小字、花体、低分辨率、倾斜和反光敏感；
- 当前读数公式默认刻度均匀；
- 双指针表、多圈表、非线性刻度表需要额外开发。

工程上建议保留手动校准入口作为可靠兜底方案。
