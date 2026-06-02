package com.example.ragshoppingagent.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.example.ragshoppingagent.model.ChatMessage
import com.example.ragshoppingagent.model.ProductCard
import com.example.ragshoppingagent.model.Role
import com.example.ragshoppingagent.viewmodel.ChatViewModel

@Composable
fun ChatRoute(viewModel: ChatViewModel = viewModel()) {
    val state by viewModel.uiState.collectAsState()
    ChatScreen(
        messages = state.messages,
        products = state.products,
        input = state.input,
        isStreaming = state.isStreaming,
        onInputChange = viewModel::onInputChange,
        onSend = viewModel::sendMessage,
    )
}

@Composable
fun ChatScreen(
    messages: List<ChatMessage>,
    products: List<ProductCard>,
    input: String,
    isStreaming: Boolean,
    onInputChange: (String) -> Unit,
    onSend: () -> Unit,
) {
    var selectedProduct by remember { mutableStateOf<ProductCard?>(null) }

    Scaffold(
        bottomBar = {
            MessageComposer(
                value = input,
                enabled = !isStreaming,
                onValueChange = onInputChange,
                onSend = onSend,
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background)
                .padding(padding),
        ) {
            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(messages, key = { it.id }) { message ->
                    MessageBubble(message)
                }
            }

            if (products.isNotEmpty()) {
                LazyRow(
                    modifier = Modifier.fillMaxWidth(),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(products, key = { it.id }) { product ->
                        ProductCardItem(product, onOpen = { selectedProduct = it })
                    }
                }
            }
        }
    }

    selectedProduct?.let { product ->
        ProductDetailDialog(
            product = product,
            onDismiss = { selectedProduct = null },
        )
    }
}

@Composable
private fun MessageBubble(message: ChatMessage) {
    val isUser = message.role == Role.User
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Surface(
            color = if (isUser) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface,
            shape = RoundedCornerShape(8.dp),
            tonalElevation = if (isUser) 0.dp else 1.dp,
            modifier = Modifier.fillMaxWidth(0.84f),
        ) {
            Text(
                text = message.text.ifEmpty { " " },
                color = if (isUser) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
            )
        }
    }
}

@Composable
private fun ProductCardItem(product: ProductCard, onOpen: (ProductCard) -> Unit) {
    Card(
        onClick = { onOpen(product) },
        modifier = Modifier.width(232.dp),
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(
            modifier = Modifier
                .heightIn(min = 260.dp)
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            ProductImage(
                imageUrl = product.imageUrl,
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1.25f)
                    .clip(RoundedCornerShape(6.dp)),
            )
            Text(
                text = product.name,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                maxLines = 3,
            )
            Text(text = product.brand, style = MaterialTheme.typography.labelMedium)
            Text(
                text = "¥${product.price.toInt()}",
                color = MaterialTheme.colorScheme.primary,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = product.reason,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 3,
            )
        }
    }
}

@Composable
private fun ProductDetailDialog(product: ProductCard, onDismiss: () -> Unit) {
    val uriHandler = LocalUriHandler.current

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(text = product.name, style = MaterialTheme.typography.titleMedium)
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                ProductImage(
                    imageUrl = product.imageUrl,
                    modifier = Modifier
                        .fillMaxWidth()
                        .aspectRatio(1.35f)
                        .clip(RoundedCornerShape(8.dp)),
                )
                Text(text = "${product.brand} · ${product.category}", style = MaterialTheme.typography.labelLarge)
                Text(
                    text = "¥${product.price.toInt()}",
                    color = MaterialTheme.colorScheme.primary,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(text = product.reason, style = MaterialTheme.typography.bodyMedium)
            }
        },
        confirmButton = {
            if (product.detailUrl.isNotBlank()) {
                TextButton(onClick = { uriHandler.openUri(product.detailUrl) }) {
                    Text("打开链接")
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("关闭")
            }
        },
    )
}

@Composable
private fun ProductImage(imageUrl: String, modifier: Modifier = Modifier) {
    var failed by remember(imageUrl) { mutableStateOf(false) }

    if (imageUrl.isBlank() || failed) {
        Box(
            modifier = modifier.background(MaterialTheme.colorScheme.surfaceVariant),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = "暂无图片",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.labelMedium,
            )
        }
        return
    }

    AsyncImage(
        model = imageUrl,
        contentDescription = null,
        contentScale = ContentScale.Crop,
        onError = { failed = true },
        modifier = modifier.background(MaterialTheme.colorScheme.surfaceVariant),
    )
}

@Composable
private fun MessageComposer(
    value: String,
    enabled: Boolean,
    onValueChange: (String) -> Unit,
    onSend: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            modifier = Modifier.weight(1f),
            enabled = enabled,
            minLines = 1,
            maxLines = 3,
            placeholder = { Text("说说你想买什么") },
        )
        IconButton(
            onClick = onSend,
            enabled = enabled && value.isNotBlank(),
        ) {
            Icon(imageVector = Icons.Filled.Send, contentDescription = "发送")
        }
    }
}

@Preview
@Composable
private fun ChatScreenPreview() {
    RagShoppingAgentTheme {
        ChatScreen(
            messages = listOf(
                ChatMessage("1", Role.User, "推荐一款适合油皮的洗面奶"),
                ChatMessage("2", Role.Assistant, "根据当前商品库检索结果，更匹配你这次需求的是..."),
            ),
            products = listOf(
                ProductCard(
                    id = "p_beauty_021",
                    name = "科颜氏牛油果保湿眼霜滋润补水细腻质地淡化干纹眼周护理28g",
                    category = "美妆护肤",
                    brand = "科颜氏",
                    price = 210.0,
                    imageUrl = "http://127.0.0.1:8000/assets/products/p_beauty_021_live.jpg",
                    detailUrl = "",
                    reason = "匹配眼霜需求",
                ),
            ),
            input = "",
            isStreaming = false,
            onInputChange = {},
            onSend = {},
        )
    }
}
