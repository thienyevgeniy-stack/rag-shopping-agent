package com.example.ragshoppingagent.model

data class ChatMessage(
    val id: String,
    val role: Role,
    val text: String,
)

enum class Role {
    User,
    Assistant,
}
