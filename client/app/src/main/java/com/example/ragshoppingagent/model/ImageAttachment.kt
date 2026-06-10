package com.example.ragshoppingagent.model

data class ImageAttachment(
    val uri: String,
    val bytes: ByteArray,
    val mimeType: String,
    val filename: String,
) {
    val hasContent: Boolean
        get() = bytes.isNotEmpty()
}
