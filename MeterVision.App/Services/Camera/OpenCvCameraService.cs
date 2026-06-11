using OpenCvSharp;

namespace MeterVision.App.Services.Camera;

public sealed class OpenCvCameraService : IDisposable
{
    private VideoCapture? _capture;

    public bool IsRunning => _capture?.IsOpened() == true;

    public int CameraIndex { get; private set; } = -1;

    public string LastError { get; private set; } = "";

    public bool Start(int cameraIndex)
    {
        Stop();

        try
        {
            var capture = new VideoCapture();
            capture.Open(cameraIndex, VideoCaptureAPIs.DSHOW);

            if (!capture.IsOpened())
            {
                capture.Dispose();
                LastError = $"摄像头 {cameraIndex} 打开失败。";
                return false;
            }

            capture.Set(VideoCaptureProperties.FrameWidth, 1280);
            capture.Set(VideoCaptureProperties.FrameHeight, 720);

            _capture = capture;
            CameraIndex = cameraIndex;
            LastError = "";
            return true;
        }
        catch (Exception ex)
        {
            LastError = $"摄像头 {cameraIndex} 打开异常：{ex.Message}";
            Stop();
            return false;
        }
    }

    public Mat? ReadFrame()
    {
        if (!IsRunning || _capture is null)
        {
            return null;
        }

        var frame = new Mat();
        if (!_capture.Read(frame) || frame.Empty())
        {
            frame.Dispose();
            LastError = "摄像头读取画面失败。";
            return null;
        }

        return frame;
    }

    public void Stop()
    {
        if (_capture is not null)
        {
            _capture.Release();
            _capture.Dispose();
            _capture = null;
        }

        CameraIndex = -1;
    }

    public void Dispose()
    {
        Stop();
    }
}
