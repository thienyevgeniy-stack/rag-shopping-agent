package com.example.ragshoppingagent.viewmodel

import androidx.lifecycle.ViewModel
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
    val input: String = "",
    val isStreaming: Boolean = false,
)

class ChatViewModel : ViewModel() {
    private val client = ChatSseClient()
    private val sessionId = UUID.randomUUID().toString()

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState

    fun onInputChange(value: String) {
        _uiState.update { it.copy(input = value) }
    }

    fun sendMessage() {
        val text = _uiState.value.input.trim()
        if (text.isEmpty() || _uiState.value.isStreaming) return

        val assistantId = UUID.randomUUID().toString()
        _uiState.update {
            it.copy(
                input = "",
                isStreaming = true,
                products = emptyList(),
                comparison = null,
                messages = it.messages +
                    ChatMessage(UUID.randomUUID().toString(), Role.User, text) +
                    ChatMessage(assistantId, Role.Assistant, ""),
            )
        }

        client.send(
            sessionId = sessionId,
            message = text,
            onToken = { token -> appendAssistantToken(assistantId, token) },
            onProduct = { product -> _uiState.update { it.copy(products = it.products + product) } },
            onComparison = { comparison -> _uiState.update { it.copy(comparison = comparison) } },
            onDone = { _uiState.update { it.copy(isStreaming = false) } },
            onError = { error ->
                appendAssistantToken(assistantId, "\n请求失败：${error.message ?: "未知错误"}")
                _uiState.update { it.copy(isStreaming = false) }
            },
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
