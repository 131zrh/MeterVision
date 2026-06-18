package com.metervision.android

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.Locale
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {
    private lateinit var previewView: PreviewView
    private lateinit var serverUrlInput: EditText
    private lateinit var fullRangeInput: EditText
    private lateinit var targetPressureInput: EditText
    private lateinit var toleranceInput: EditText
    private lateinit var unitInput: EditText
    private lateinit var statusText: TextView
    private lateinit var resultText: TextView

    private var imageCapture: ImageCapture? = null
    private lateinit var cameraExecutor: ExecutorService

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .readTimeout(180, TimeUnit.SECONDS)
        .build()

    private val cameraPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) {
                startCamera()
            } else {
                setStatus("未授予相机权限，无法拍照。", true)
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        cameraExecutor = Executors.newSingleThreadExecutor()
        buildUi()

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(243, 245, 247))
        }

        previewView = PreviewView(this).apply {
            scaleType = PreviewView.ScaleType.FIT_CENTER
            setBackgroundColor(Color.rgb(17, 24, 39))
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1f,
            )
        }
        root.addView(previewView)

        val controls = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 18, 24, 24)
        }

        serverUrlInput = createInput("http://10.0.2.2:5080/api/infer")
        fullRangeInput = createInput("5")
        targetPressureInput = createInput("1.0")
        toleranceInput = createInput("0.05")
        unitInput = createInput("MPa")

        controls.addView(createLabel("识别服务地址（真机用 http://电脑IP:5080/api/infer）"))
        controls.addView(serverUrlInput)
        controls.addView(createTwoColumnRow("量程", fullRangeInput, "单位", unitInput))
        controls.addView(createTwoColumnRow("给定压力", targetPressureInput, "允许误差", toleranceInput))

        val captureButton = Button(this).apply {
            text = "拍照并识别"
            setOnClickListener { takePhotoAndUpload() }
        }
        controls.addView(captureButton)

        statusText = TextView(this).apply {
            text = "准备中..."
            setTextColor(Color.rgb(75, 85, 99))
            textSize = 14f
            setPadding(0, 10, 0, 8)
        }
        controls.addView(statusText)

        resultText = TextView(this).apply {
            text = "识别结果会显示在这里。"
            setTextColor(Color.rgb(31, 41, 55))
            textSize = 16f
            setPadding(0, 4, 0, 0)
        }
        controls.addView(resultText)

        root.addView(ScrollView(this).apply {
            addView(controls)
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            )
        })

        setContentView(root)
    }

    private fun createLabel(textValue: String): TextView {
        return TextView(this).apply {
            text = textValue
            setTextColor(Color.rgb(55, 65, 81))
            textSize = 13f
            setPadding(0, 6, 0, 4)
        }
    }

    private fun createInput(value: String): EditText {
        return EditText(this).apply {
            setText(value)
            singleLine = true
            textSize = 14f
            setPadding(12, 6, 12, 6)
        }
    }

    private fun createTwoColumnRow(
        leftLabel: String,
        leftInput: EditText,
        rightLabel: String,
        rightInput: EditText,
    ): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(createField(leftLabel, leftInput), LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(createField(rightLabel, rightInput), LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
    }

    private fun createField(label: String, input: EditText): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 0, 12, 0)
            addView(createLabel(label))
            addView(input)
        }
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }

            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .build()

            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(
                    this,
                    CameraSelector.DEFAULT_BACK_CAMERA,
                    preview,
                    imageCapture,
                )
                setStatus("相机已启动。", false)
            } catch (ex: Exception) {
                setStatus("相机启动失败：${ex.message}", true)
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun takePhotoAndUpload() {
        val capture = imageCapture
        if (capture == null) {
            setStatus("相机尚未准备好。", true)
            return
        }

        val imageFile = File(cacheDir, "meter_${System.currentTimeMillis()}.jpg")
        val outputOptions = ImageCapture.OutputFileOptions.Builder(imageFile).build()
        setStatus("正在拍照...", false)

        capture.takePicture(
            outputOptions,
            cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onError(exception: ImageCaptureException) {
                    runOnUiThread { setStatus("拍照失败：${exception.message}", true) }
                }

                override fun onImageSaved(outputFileResults: ImageCapture.OutputFileResults) {
                    uploadImage(imageFile)
                }
            },
        )
    }

    private fun uploadImage(imageFile: File) {
        runOnUiThread { setStatus("正在上传并识别...", false) }

        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("fullRange", fullRangeInput.text.toString())
            .addFormDataPart("targetPressure", targetPressureInput.text.toString())
            .addFormDataPart("tolerance", toleranceInput.text.toString())
            .addFormDataPart("unit", unitInput.text.toString())
            .addFormDataPart(
                "image",
                imageFile.name,
                imageFile.asRequestBody("image/jpeg".toMediaType()),
            )
            .build()

        val request = Request.Builder()
            .url(serverUrlInput.text.toString())
            .post(requestBody)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread { setStatus("上传失败：${e.message}", true) }
            }

            override fun onResponse(call: Call, response: Response) {
                val body = response.body?.string().orEmpty()
                runOnUiThread {
                    if (!response.isSuccessful) {
                        setStatus("服务返回错误：${response.code}", true)
                        resultText.text = body
                        return@runOnUiThread
                    }

                    showResult(body)
                }
            }
        })
    }

    private fun showResult(jsonText: String) {
        try {
            val json = JSONObject(jsonText)
            val success = json.optBoolean("success")
            val message = json.optString("message", "")

            if (!success) {
                setStatus("识别失败：$message", true)
                resultText.text = jsonText
                return
            }

            val reading = json.optDouble("reading")
            val target = json.optDouble("targetPressure")
            val error = json.optDouble("error")
            val tolerance = json.optDouble("tolerance")
            val unit = json.optString("unit", "MPa")
            val passed = json.optBoolean("passed")
            val result = if (passed) "合格" else "不合格"

            setStatus("识别完成。", false)
            resultText.text = String.format(
                Locale.US,
                "读数：%.3f %s\n给定：%.3f %s\n误差：%+.3f %s\n允许误差：±%.3f %s\n结论：%s",
                reading,
                unit,
                target,
                unit,
                error,
                unit,
                tolerance,
                unit,
                result,
            )
        } catch (ex: Exception) {
            setStatus("结果解析失败：${ex.message}", true)
            resultText.text = jsonText
        }
    }

    private fun setStatus(message: String, isError: Boolean) {
        statusText.text = message
        statusText.setTextColor(if (isError) Color.rgb(185, 28, 28) else Color.rgb(75, 85, 99))
    }
}
