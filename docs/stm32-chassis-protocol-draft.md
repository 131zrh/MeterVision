# STM32 底盘通信协议草案

本文档用于下周和硬件老师确认，不代表最终协议。

## 1. 通信方式

- 物理连接：USB
- 推荐设备类型：USB CDC 虚拟串口
- 电脑端表现：Windows 设备管理器中显示为 COM 口，例如 COM3、COM4
- 推荐波特率：115200
- 数据位：8
- 停止位：1
- 校验位：None
- 换行符：`\r\n`

## 2. 第一阶段推荐使用文本协议

前期目标是快速联调，因此建议先用文本命令。优点是可以用串口助手直接测试，方便排查问题。

## 3. 上位机发送命令

| 命令 | 示例 | 含义 |
| --- | --- | --- |
| `UP <steps>` | `UP 1` | 底盘上升指定步数 |
| `DOWN <steps>` | `DOWN 1` | 底盘下降指定步数 |
| `ROTATE_LEFT <steps>` | `ROTATE_LEFT 1` | 底盘向左旋转指定步数 |
| `ROTATE_RIGHT <steps>` | `ROTATE_RIGHT 1` | 底盘向右旋转指定步数 |
| `STOP` | `STOP` | 立即停止当前动作 |
| `HOME` | `HOME` | 底盘回零 |
| `GET_STATUS` | `GET_STATUS` | 查询当前状态 |

## 4. STM32 返回格式

建议每条命令都返回一行文本。

```text
OK <command> <message>
ERR <code> <message>
STATUS LIFT=<value> ROTATE=<value> BUSY=<0|1> HOMED=<0|1>
```

示例：

```text
OK UP DONE
OK STOP DONE
ERR LIMIT_UP 上升限位已触发
STATUS LIFT=120 ROTATE=-8 BUSY=0 HOMED=1
```

## 5. 必须确认的问题

1. STM32 插入电脑后是否显示为 COM 口。
2. 如果是 COM 口，默认波特率是多少。
3. 底盘升降的单位是步数、毫米，还是脉冲数。
4. 底盘旋转的单位是步数、角度，还是脉冲数。
5. 是否有上限位、下限位、原点开关。
6. 回零流程由 STM32 内部完成，还是上位机一步步控制。
7. 急停 `STOP` 是否任何状态下都必须立即响应。
8. STM32 是否会主动上报状态，还是只能上位机查询。

## 6. 后续产品化可升级方向

如果文本协议联调通过，后续可升级为：

- 文本协议加校验字段
- 固定帧二进制协议
- Modbus RTU

第一阶段不建议一开始就做复杂协议，先把动作和流程跑通。
