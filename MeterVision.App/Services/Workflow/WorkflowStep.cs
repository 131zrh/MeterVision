namespace MeterVision.App.Services.Workflow;

public enum WorkflowStep
{
    Idle,
    CameraPreview,
    DialDetection,
    ChassisAdjusting,
    Centered,
    CaptureReady
}
