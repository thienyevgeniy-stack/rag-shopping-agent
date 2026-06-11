package com.example.ragshoppingagent.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.ragshoppingagent.model.CartItem
import com.example.ragshoppingagent.model.CartState
import com.example.ragshoppingagent.model.ChatMessage
import com.example.ragshoppingagent.model.ChatSessionSummary
import com.example.ragshoppingagent.model.ComparisonCard
import com.example.ragshoppingagent.model.ComparisonProduct
import com.example.ragshoppingagent.model.ComparisonRecommendation
import com.example.ragshoppingagent.model.ProductCard
import com.example.ragshoppingagent.model.Role
import com.example.ragshoppingagent.viewmodel.ChatViewModel
import kotlinx.coroutines.launch

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
        selectedImageUri = state.selectedImage?.uri.orEmpty(),
        sessions = state.sessions,
        activeSessionId = state.activeSessionId,
        isLoadingSessions = state.isLoadingSessions,
        onInputChange = viewModel::onInputChange,
        onAttachImage = viewModel::attachImage,
        onClearImage = viewModel::clearImage,
        onSend = viewModel::sendMessage,
        onAddToCart = viewModel::addProductToCart,
        onIncrementCart = viewModel::incrementProductInCart,
        onDecrementCart = viewModel::decrementProductInCart,
        onNewSession = viewModel::newSession,
        onRefreshCart = viewModel::refreshCart,
        onRefreshSessions = viewModel::refreshSessions,
        onOpenSession = viewModel::openSession,
        onResetSession = viewModel::resetSession,
        onDeleteSession = viewModel::deleteSession,
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
    sessions: List<ChatSessionSummary>,
    activeSessionId: String,
    isLoadingSessions: Boolean,
    onInputChange: (String) -> Unit,
    onAttachImage: (String, ByteArray, String, String) -> Unit,
    onClearImage: () -> Unit,
    onSend: () -> Unit,
    onAddToCart: (ProductCard) -> Unit,
    onIncrementCart: (ProductCard) -> Unit,
    onDecrementCart: (ProductCard) -> Unit,
    onNewSession: () -> Unit,
    onRefreshCart: () -> Unit,
    onRefreshSessions: () -> Unit,
    onOpenSession: (String) -> Unit,
    onResetSession: () -> Unit,
    onDeleteSession: (String) -> Unit,
) {
    var selectedProduct by remember { mutableStateOf<ProductCard?>(null) }
    var pendingDeleteSession by remember { mutableStateOf<ChatSessionSummary?>(null) }
    var showCart by remember { mutableStateOf(false) }
    val historyDrawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
    val coroutineScope = rememberCoroutineScope()
    val currentCart = cart ?: CartState.empty()
    val context = LocalContext.current
    val imagePicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
    ) { uri ->
        if (uri != null) {
            val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            if (bytes != null) {
                val mimeType = context.contentResolver.getType(uri) ?: "image/jpeg"
                onAttachImage(uri.toString(), bytes, mimeType, uri.lastPathSegment ?: "picked_image")
            }
        }
    }

    ModalNavigationDrawer(
        drawerState = historyDrawerState,
        drawerContent = {
            ModalDrawerSheet(
                modifier = Modifier
                    .fillMaxHeight()
                    .width(320.dp),
            ) {
                HistoryDrawerContent(
                    sessions = sessions,
                    activeSessionId = activeSessionId,
                    isLoading = isLoadingSessions,
                    onDismiss = {
                        coroutineScope.launch { historyDrawerState.close() }
                    },
                    onOpenSession = { session ->
                        onOpenSession(session.sessionId)
                        coroutineScope.launch { historyDrawerState.close() }
                    },
                    onNewSession = {
                        onNewSession()
                        coroutineScope.launch { historyDrawerState.close() }
                    },
                    onRefreshSessions = onRefreshSessions,
                    onResetSession = {
                        onResetSession()
                        coroutineScope.launch { historyDrawerState.close() }
                    },
                    onDeleteSession = { session ->
                        pendingDeleteSession = session
                    },
                )
            }
        },
    ) {
        Scaffold(
            topBar = {
                ShoppingAssistantTopBar(
                    cart = currentCart,
                    onOpenCart = {
                        onRefreshCart()
                        showCart = true
                    },
                    onNewSession = onNewSession,
                    onOpenHistory = {
                        onRefreshSessions()
                        coroutineScope.launch { historyDrawerState.open() }
                    },
                )
            },
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

                comparison?.let {
                    ComparisonPanel(
                        comparison = it,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    )
                }

                if (products.isNotEmpty()) {
                    ProductCarousel(
                        products = products,
                        cart = currentCart,
                        onOpen = { selectedProduct = it },
                        onAddToCart = onAddToCart,
                        onIncrementCart = onIncrementCart,
                        onDecrementCart = onDecrementCart,
                    )
                }
            }
        }
    }

    selectedProduct?.let { product ->
        ProductDetailDialog(
            product = product,
            cartQuantity = currentCart.quantityFor(product.id),
            onDismiss = { selectedProduct = null },
            onAddToCart = onAddToCart,
            onIncrementCart = onIncrementCart,
            onDecrementCart = onDecrementCart,
        )
    }

    if (showCart) {
        CartDialog(
            cart = currentCart,
            onDismiss = { showCart = false },
            onOpenItem = { item ->
                selectedProduct = item.toProductCard()
                showCart = false
            },
        )
    }

    pendingDeleteSession?.let { session ->
        AlertDialog(
            onDismissRequest = { pendingDeleteSession = null },
            title = { Text("删除历史对话") },
            text = {
                Text("确定删除“${session.title.ifBlank { "新对话" }}”吗？删除后不会影响其他对话。")
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        onDeleteSession(session.sessionId)
                        pendingDeleteSession = null
                    },
                ) {
                    Text("删除")
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingDeleteSession = null }) {
                    Text("取消")
                }
            },
        )
    }
}

@Composable
private fun ProductCarousel(
    products: List<ProductCard>,
    cart: CartState,
    onOpen: (ProductCard) -> Unit,
    onAddToCart: (ProductCard) -> Unit,
    onIncrementCart: (ProductCard) -> Unit,
    onDecrementCart: (ProductCard) -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 1.dp,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 340.dp)
                .padding(top = 10.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = "商品推荐",
                modifier = Modifier.padding(horizontal = 16.dp),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
            )
            LazyRow(
                modifier = Modifier.fillMaxWidth(),
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                userScrollEnabled = true,
            ) {
                items(products, key = { it.id }) { product ->
                    ProductCardItem(
                        product = product,
                        cartQuantity = cart.quantityFor(product.id),
                        onOpen = { onOpen(it) },
                        onAddToCart = onAddToCart,
                        onIncrementCart = onIncrementCart,
                        onDecrementCart = onDecrementCart,
                    )
                }
            }
        }
    }
}

@Composable
private fun ShoppingAssistantTopBar(
    cart: CartState,
    onOpenCart: () -> Unit,
    onNewSession: () -> Unit,
    onOpenHistory: () -> Unit,
) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 2.dp,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onOpenHistory) {
                Icon(
                    imageVector = Icons.Filled.History,
                    contentDescription = "历史对话",
                )
            }
            Column(
                modifier = Modifier.weight(1f),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    text = "RAG 导购",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = "商品问答 · 比选 · 加购",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    textAlign = TextAlign.Center,
                )
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onNewSession) {
                    Icon(
                        imageVector = Icons.Filled.Add,
                        contentDescription = "新建对话",
                    )
                }
                IconButton(onClick = onOpenCart) {
                    BadgedBox(
                        badge = {
                            if (cart.totalQuantity > 0) {
                                Badge {
                                    Text(if (cart.totalQuantity > 99) "99+" else cart.totalQuantity.toString())
                                }
                            }
                        },
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ShoppingCart,
                            contentDescription = "打开购物车",
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun HistoryDrawerContent(
    sessions: List<ChatSessionSummary>,
    activeSessionId: String,
    isLoading: Boolean,
    onDismiss: () -> Unit,
    onOpenSession: (ChatSessionSummary) -> Unit,
    onNewSession: () -> Unit,
    onRefreshSessions: () -> Unit,
    onResetSession: () -> Unit,
    onDeleteSession: (ChatSessionSummary) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxHeight()
            .padding(vertical = 12.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 20.dp, end = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "历史对话",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = "最近会话和购物车状态",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Row(
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (isLoading) {
                    CircularProgressIndicator(modifier = Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                }
                IconButton(onClick = onRefreshSessions) {
                    Icon(
                        imageVector = Icons.Filled.Refresh,
                        contentDescription = "刷新历史对话",
                    )
                }
                IconButton(onClick = onDismiss) {
                    Icon(
                        imageVector = Icons.Filled.Close,
                        contentDescription = "关闭历史侧栏",
                    )
                }
            }
        }

        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 12.dp)
                .clickable(onClick = onNewSession),
            color = MaterialTheme.colorScheme.primaryContainer,
            contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
            shape = MaterialTheme.shapes.medium,
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    imageVector = Icons.Filled.Add,
                    contentDescription = null,
                )
                Text(
                    text = "新建对话",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }

        HorizontalDivider()

        if (sessions.isEmpty() && !isLoading) {
            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    text = "还没有历史对话。发送一次问题后，这里会显示最近的会话。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    textAlign = TextAlign.Center,
                )
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(sessions, key = { it.sessionId }) { session ->
                    HistorySessionRow(
                        session = session,
                        isActive = session.sessionId == activeSessionId,
                        onClick = { onOpenSession(session) },
                        onDelete = { onDeleteSession(session) },
                    )
                }
            }
        }

        HorizontalDivider()

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "当前会话可重置",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            TextButton(onClick = onResetSession) {
                Text("重置当前")
            }
        }
    }
}

@Composable
private fun HistorySessionRow(
    session: ChatSessionSummary,
    isActive: Boolean,
    onClick: () -> Unit,
    onDelete: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        color = if (isActive) {
            MaterialTheme.colorScheme.primaryContainer
        } else {
            MaterialTheme.colorScheme.surfaceVariant
        },
        contentColor = if (isActive) {
            MaterialTheme.colorScheme.onPrimaryContainer
        } else {
            MaterialTheme.colorScheme.onSurfaceVariant
        },
        shape = MaterialTheme.shapes.small,
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = session.title.ifBlank { "新对话" },
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                if (isActive) {
                    Text(
                        text = "当前",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
                IconButton(onClick = onDelete) {
                    Icon(
                        imageVector = Icons.Filled.Delete,
                        contentDescription = "删除历史对话",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (session.summary.isNotBlank()) {
                Text(
                    text = session.summary,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Text(
                text = "${session.messageCount} 条消息 · 购物车 ${session.cartQuantity} 件",
                style = MaterialTheme.typography.labelSmall,
            )
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
            sessions = listOf(
                ChatSessionSummary(
                    sessionId = "preview-session",
                    title = "推荐一款保湿眼霜",
                    summary = "最近需求：保湿眼霜，预算 250 以内。",
                    updatedAt = 0.0,
                    messageCount = 2,
                    cartQuantity = 1,
                ),
            ),
            activeSessionId = "preview-session",
            isLoadingSessions = false,
            onInputChange = {},
            onAttachImage = { _, _, _, _ -> },
            onClearImage = {},
            onSend = {},
            onAddToCart = {},
            onIncrementCart = {},
            onDecrementCart = {},
            onNewSession = {},
            onRefreshCart = {},
            onRefreshSessions = {},
            onOpenSession = {},
            onResetSession = {},
            onDeleteSession = {},
        )
    }
}
