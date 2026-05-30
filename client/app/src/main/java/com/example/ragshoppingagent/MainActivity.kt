package com.example.ragshoppingagent

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.example.ragshoppingagent.ui.ChatRoute
import com.example.ragshoppingagent.ui.RagShoppingAgentTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            RagShoppingAgentTheme {
                ChatRoute()
            }
        }
    }
}
