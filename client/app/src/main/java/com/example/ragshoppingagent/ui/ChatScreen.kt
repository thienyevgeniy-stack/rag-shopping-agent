package com.example.ragshoppingagent.ui

import android.util.Base64
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.ragshoppingagent.model.CartItem
import com.example.ragshoppingagent.model.CartState
import com.example.ragshoppingagent.model.ChatMessage
import com.example.ragshoppingagent.model.ComparisonCard
import com.example.ragshoppingagent.model.ComparisonProduct
import com.example.ragshoppingagent.model.ComparisonRecommendation
import com.example.ragshoppingagent.model.ProductCard
import com.example.ragshoppingagent.model.Role
import com.example.ragshoppingagent.viewmodel.ChatViewModel

@Composable
fun ChatRoute(viewModel: ChatViewModel = viewModel()) {
    val state by viewModel.uiState.collectAsState()
    ChatScreen(
        messages = state.messages,
        products = state.products,
        comparison = state.comparison,
        cart = state.cart,
        input = state.input,
        isStreaming = state.isStreaming,
        selectedImageUri = state.selectedImageUri,
        onInputChange = viewModel::onInputChange,
        onAttachImage = viewModel::attachImage,
        onClearImage = viewModel::clearImage,
        onSend = viewModel::sendMessage,
    )
}

@Composable
fun ChatScreen(
    messages: List<ChatMessage>,
    products: List<ProductCard>,
    comparison: ComparisonCard?,
    cart: CartState?,
    input: String,
    isStreaming: Boolean,
    selectedImageUri: String,
    onInputChange: (String) -> Unit,
    onAttachImage: (String, String, String, String) -> Unit,
    onClearImage: () -> Unit,
    onSend: () -> Unit,
) {
    var selectedProduct by remember { mutableStateOf<ProductCard?>(null) }
    val context = LocalContext.current
    val imagePicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
    ) { uri ->
        if (uri != null) {
            val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            if (bytes != null) {
                val encoded = Base64.encodeToString(bytes, Base64.NO_WRAP)
                val mimeType = context.contentResolver.getType(uri) ?: "image/jpeg"
                onAttachImage(uri.toString(), encoded, mimeType, uri.lastPathSegment ?: "picked_image")
            }
        }
    }

    Scaffold(
        bottomBar = {
            MessageComposer(
                value = input,
                enabled = !isStreaming,
                selectedImageUri = selectedImageUri,
                onValueChange = onInputChange,
                onPickImage = {
                    imagePicker.launch(
                        PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly),
                    )
                },
                onClearImage = onClearImage,
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

            cart?.let {
                CartPanel(
                    cart = it,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    onOpenItem = { item -> selectedProduct = item.toProductCard() },
                )
            }

            comparison?.let {
                ComparisonPanel(
                    comparison = it,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                )
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
            comparison = ComparisonCard(
                title = "商品对比",
                query = "科颜氏和AHC哪个眼霜更适合干皮",
                products = listOf(
                    ComparisonProduct(
                        id = "p_beauty_021",
                        name = "科颜氏牛油果保湿眼霜滋润补水细腻质地淡化干纹眼周护理28g",
                        brand = "科颜氏",
                        category = "美妆护肤",
                        price = 210.0,
                        reason = "匹配 眼霜, 科颜氏 等需求",
                        strengths = listOf("保湿", "补水"),
                        tradeoffs = listOf("需结合个人偏好确认"),
                    ),
                    ComparisonProduct(
                        id = "p_beauty_016",
                        name = "AHC塑颜修护全脸眼霜紧致淡纹保湿提亮多效眼周护理30ml",
                        brand = "AHC",
                        category = "美妆护肤",
                        price = 139.0,
                        reason = "匹配 眼霜, AHC 等需求",
                        strengths = listOf("保湿", "修护"),
                        tradeoffs = listOf("价格更低"),
                    ),
                ),
                recommendation = ComparisonRecommendation(
                    productId = "p_beauty_021",
                    productName = "科颜氏牛油果保湿眼霜滋润补水细腻质地淡化干纹眼周护理28g",
                    focus = "保湿/干皮",
                    summary = "更偏向 保湿/干皮 时，优先看 科颜氏牛油果保湿眼霜。",
                ),
            ),
            cart = CartState(
                items = listOf(
                    CartItem(
                        productId = "p_beauty_021",
                        name = "科颜氏牛油果保湿眼霜滋润补水细腻质地淡化干纹眼周护理28g",
                        brand = "科颜氏",
                        category = "美妆护肤",
                        price = 210.0,
                        quantity = 1,
                        imageUrl = "",
                        detailUrl = "",
                    ),
                ),
                totalQuantity = 1,
                totalPrice = 210.0,
                isEmpty = false,
            ),
            input = "",
            isStreaming = false,
            selectedImageUri = "",
            onInputChange = {},
            onAttachImage = { _, _, _, _ -> },
            onClearImage = {},
            onSend = {},
        )
    }
}
