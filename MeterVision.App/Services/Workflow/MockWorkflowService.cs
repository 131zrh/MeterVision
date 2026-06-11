namespace MeterVision.App.Services.Workflow;

public sealed class MockWorkflowService : IWorkflowService
{
    public WorkflowStatus Current { get; private set; } =
        new(WorkflowStep.Idle, "流程空闲。", DateTime.Now);

    public WorkflowStatus StartAutoCenter()
    {
        Current = new WorkflowStatus(
            WorkflowStep.ChassisAdjusting,
            "模拟自动对中流程已启动。后续会接入表盘中心检测和底盘微调。",
            DateTime.Now);

        return Current;
    }

    public WorkflowStatus CaptureFrame()
    {
        Current = new WorkflowStatus(
            WorkflowStep.CaptureReady,
            "模拟采集当前画面。后续会接入 USB 摄像头截图。",
            DateTime.Now);

        return Current;
    }

    public WorkflowStatus Reset()
    {
        Current = new WorkflowStatus(WorkflowStep.Idle, "流程已复位。", DateTime.Now);
        return Current;
    }
}
