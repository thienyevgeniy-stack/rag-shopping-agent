package com.example.ragshoppingagent.viewmodel

import androidx.lifecycle.ViewModel
import com.example.ragshoppingagent.model.CartState
import com.example.ragshoppingagent.model.ChatMessage
import com.example.ragshoppingagent.model.ComparisonCard
import com.example.ragshoppingagent.model.ProductCard
import com.example.ragshoppingagent.model.Role
import com.example.ragshoppingagent.network.ChatSseClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import java.util.UUID

data class ChatUiState(
    val messages: List<ChatMessage> = emptyList(),
    val products: List<ProductCard> = emptyList(),
    val comparison: ComparisonCard? = null,
    val cart: CartState? = null,
    val input: String = "",
    val isStreaming: Boolean = false,
    val selectedImageUri: String = "",
    val selectedImageBase64: String = "",
    val selectedImageMimeType: String = "",
    val selectedImageName: String = "",
)

class ChatViewModel : ViewModel() {
    private val client = ChatSseClient()
    private val sessionId = UUID.randomUUID().toString()

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState

    fun onInputChange(value: String) {
        _uiState.update { it.copy(input = value) }
    }

    fun attachImage(uri: String, base64: String, mimeType: String, name: String) {
        _uiState.update {
            it.copy(
                selectedImageUri = uri,
                selectedImageBase64 = base64,
                selectedImageMimeType = mimeType,
                selectedImageName = name,
            )
        }
    }

    fun clearImage() {
        _uiState.update {
            it.copy(
                selectedImageUri = "",
                selectedImageBase64 = "",
                selectedImageMimeType = "",
                selectedImageName = "",
            )
        }
    }

    fun sendMessage() {
        val current = _uiState.value
        val hasImage = current.selectedImageBase64.isNotBlank()
        val text = current.input.trim()
        if ((text.isEmpty() && !hasImage) || current.isStreaming) return
        val messageText = text.ifEmpty { "我想找图片里的同款或相似商品" }

        val assistantId = UUID.randomUUID().toString()
        _uiState.update {
            it.copy(
                input = "",
                isStreaming = true,
                products = emptyList(),
                comparison = null,
                selectedImageUri = "",
                selectedImageBase64 = "",
                selectedImageMimeType = "",
                selectedImageName = "",
                messages = it.messages +
                    ChatMessage(
                        UUID.randomUUID().toString(),
                        Role.User,
                        if (hasImage) "$messageText\n[已附加图片]" else messageText,
                    ) +
                    ChatMessage(assistantId, Role.Assistant, ""),
            )
        }

        client.send(
            sessionId = sessionId,
            message = text,
            onToken = { token -> appendAssistantToken(assistantId, token) },
            onProduct = { product -> _uiState.update { it.copy(products = it.products + product) } },
            onComparison = { comparison -> _uiState.update { it.copy(comparison = comparison) } },
            onCart = { cart -> _uiState.update { it.copy(cart = cart) } },
            onImageAnalysis = { summary ->
                if (summary.isNotBlank()) {
                    appendAssistantToken(assistantId, "图片识别：$summary\n")
                }
            },
            onDone = { _uiState.update { it.copy(isStreaming = false) } },
            onError = { error ->
                appendAssistantToken(assistantId, "\n请求失败：${error.message ?: "未知错误"}")
                _uiState.update { it.copy(isStreaming = false) }
            },
            imageBase64 = current.selectedImageBase64,
            imageMimeType = current.selectedImageMimeType,
            imageFilename = current.selectedImageName,
        )
    }

    private fun appendAssistantToken(messageId: String, token: String) {
        _uiState.update { state ->
            state.copy(
                messages = state.messages.map { message ->
                    if (message.id == messageId) {
                        message.copy(text = message.text + token)
                    } else {
                        message
                    }
                },
            )
        }
    }
}
