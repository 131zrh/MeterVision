namespace MeterVision.App.Services.Workflow;

public interface IWorkflowService
{
    WorkflowStatus Current { get; }

    WorkflowStatus StartAutoCenter();

    WorkflowStatus CaptureFrame();

    WorkflowStatus Reset();
}
