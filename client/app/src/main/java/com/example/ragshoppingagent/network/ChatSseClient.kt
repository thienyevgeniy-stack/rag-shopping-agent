package com.example.ragshoppingagent.network

import com.example.ragshoppingagent.model.CartState
import com.example.ragshoppingagent.model.ComparisonCard
import com.example.ragshoppingagent.model.ProductCard
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class ChatSseClient(
    private val baseUrl: String = "http://127.0.0.1:8000",
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS)
        .build()

    suspend fun uploadImage(
        imageBytes: ByteArray,
        mimeType: String,
        filename: String,
    ): String = withContext(Dispatchers.IO) {
        val safeMimeType = mimeType.ifBlank { "image/jpeg" }
        val safeFilename = filename.ifBlank { "picked_image.jpg" }
        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart(
                "file",
                safeFilename,
                imageBytes.toRequestBody(safeMimeType.toMediaType()),
            )
            .build()

        val request = Request.Builder()
            .url("$baseUrl/uploads/images")
            .post(requestBody)
            .build()

        client.newCall(request).execute().use { response ->
            val bodyText = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw IllegalStateException("Upload failed: HTTP ${response.code} $bodyText")
            }
            JSONObject(bodyText).getString("image_id")
        }
    }

    fun send(
        sessionId: String,
        message: String,
        onToken: (String) -> Unit,
        onProduct: (ProductCard) -> Unit,
        onComparison: (ComparisonCard) -> Unit,
        onCart: (CartState) -> Unit,
        onImageAnalysis: (String) -> Unit,
        onStatus: (String) -> Unit,
        onDone: () -> Unit,
        onError: (Throwable) -> Unit,
        imageId: String = "",
        imageMimeType: String = "",
        imageFilename: String = "",
    ): EventSource {
        val body = JSONObject()
            .put("session_id", sessionId)
            .put("message", message)
            .apply {
                if (imageId.isNotBlank()) {
                    put("image_id", imageId)
                    put("image_mime_type", imageMimeType)
                    put("image_filename", imageFilename)
                }
            }
            .toString()
            .toRequestBody("application/json; charset=utf-8".toMediaType())

        val request = Request.Builder()
            .url("$baseUrl/chat")
            .post(body)
            .build()

        return EventSources.createFactory(client).newEventSource(
            request,
            object : EventSourceListener() {
                override fun onEvent(
                    eventSource: EventSource,
                    id: String?,
                    type: String?,
                    data: String,
                ) {
                    val json = JSONObject(data)
                    when (type) {
                        "token" -> onToken(json.optString("text"))
                        "product_card" -> onProduct(ProductCard.fromJson(json))
                        "comparison_card" -> onComparison(ComparisonCard.fromJson(json))
                        "cart_update" -> onCart(CartState.fromJson(json))
                        "image_analysis" -> onImageAnalysis(json.optString("summary"))
                        "status" -> onStatus(json.optString("text"))
                        "done" -> onDone()
                    }
                }

                override fun onFailure(
                    eventSource: EventSource,
                    t: Throwable?,
                    response: Response?,
                ) {
                    onError(t ?: IllegalStateException("SSE failed: ${response?.code}"))
                }
            },
        )
    }
}
