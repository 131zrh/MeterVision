namespace MeterVision.App.Services.Workflow;

public sealed record WorkflowStatus(
    WorkflowStep Step,
    string Message,
    DateTime Timestamp);
