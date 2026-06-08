package com.example.ragshoppingagent.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.ragshoppingagent.model.CartState
import com.example.ragshoppingagent.model.ChatMessage
import com.example.ragshoppingagent.model.ComparisonCard
import com.example.ragshoppingagent.model.ProductCard
import com.example.ragshoppingagent.model.Role
import com.example.ragshoppingagent.network.ChatSseClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

data class ChatUiState(
    val messages: List<ChatMessage> = emptyList(),
    val products: List<ProductCard> = emptyList(),
    val comparison: ComparisonCard? = null,
    val cart: CartState? = null,
    val input: String = "",
    val isStreaming: Boolean = false,
    val selectedImageUri: String = "",
    val selectedImageBytes: ByteArray = ByteArray(0),
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

    fun attachImage(uri: String, bytes: ByteArray, mimeType: String, name: String) {
        _uiState.update {
            it.copy(
                selectedImageUri = uri,
                selectedImageBytes = bytes,
                selectedImageMimeType = mimeType,
                selectedImageName = name,
            )
        }
    }

    fun clearImage() {
        _uiState.update {
            it.copy(
                selectedImageUri = "",
                selectedImageBytes = ByteArray(0),
                selectedImageMimeType = "",
                selectedImageName = "",
            )
        }
    }

    fun sendMessage() {
        val current = _uiState.value
        val hasImage = current.selectedImageBytes.isNotEmpty()
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
                selectedImageBytes = ByteArray(0),
                selectedImageMimeType = "",
                selectedImageName = "",
                messages = it.messages +
                    ChatMessage(
                        UUID.randomUUID().toString(),
                        Role.User,
                        if (hasImage) "$messageText\n[已附加图片]" else messageText,
                    ) +
                    ChatMessage(assistantId, Role.Assistant, "", isThinking = true),
            )
        }

        viewModelScope.launch {
            val imageId = if (hasImage) {
                uploadSelectedImageOrStop(current, assistantId) ?: return@launch
            } else {
                ""
            }

            client.send(
                sessionId = sessionId,
                message = messageText,
                onToken = { token -> appendAssistantToken(assistantId, token) },
                onProduct = { product -> _uiState.update { it.copy(products = it.products + product) } },
                onComparison = { comparison -> _uiState.update { it.copy(comparison = comparison) } },
                onCart = { cart -> _uiState.update { it.copy(cart = cart) } },
                onImageAnalysis = { summary ->
                    if (summary.isNotBlank()) {
                        appendAssistantToken(assistantId, "图片识别：$summary\n")
                    }
                },
                onStatus = { markAssistantThinking(assistantId) },
                onDone = {
                    clearAssistantThinking(assistantId)
                    _uiState.update { it.copy(isStreaming = false) }
                },
                onError = { error ->
                    appendAssistantToken(assistantId, "\n请求失败：${error.message ?: "未知错误"}")
                    _uiState.update { it.copy(isStreaming = false) }
                },
                imageId = imageId,
                imageMimeType = current.selectedImageMimeType,
                imageFilename = current.selectedImageName,
            )
        }
    }

    private suspend fun uploadSelectedImageOrStop(current: ChatUiState, assistantId: String): String? {
        return try {
            client.uploadImage(
                imageBytes = current.selectedImageBytes,
                mimeType = current.selectedImageMimeType,
                filename = current.selectedImageName,
            )
        } catch (error: Throwable) {
            appendAssistantToken(assistantId, "\n图片上传失败：${error.message ?: "未知错误"}")
            _uiState.update { it.copy(isStreaming = false) }
            null
        }
    }

    private fun appendAssistantToken(messageId: String, token: String) {
        _uiState.update { state ->
            state.copy(
                messages = state.messages.map { message ->
                    if (message.id == messageId) {
                        message.copy(text = message.text + token, isThinking = false)
                    } else {
                        message
                    }
                },
            )
        }
    }

    private fun markAssistantThinking(messageId: String) {
        _uiState.update { state ->
            state.copy(
                messages = state.messages.map { message ->
                    if (message.id == messageId && message.text.isBlank()) {
                        message.copy(isThinking = true)
                    } else {
                        message
                    }
                },
            )
        }
    }

    private fun clearAssistantThinking(messageId: String) {
        _uiState.update { state ->
            state.copy(
                messages = state.messages.map { message ->
                    if (message.id == messageId) {
                        message.copy(isThinking = false)
                    } else {
                        message
                    }
                },
            )
        }
    }
}
