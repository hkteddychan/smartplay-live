package com.playfinder.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import com.playfinder.app.alerts.WatchlistStore

@Composable
fun SettingsScreen() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var pushOn by remember { mutableStateOf(false) }
    var sports by remember { mutableStateOf(emptySet<String>()) }

    Column(Modifier.padding(16.dp).fillMaxSize()) {
        Text("設定", style = MaterialTheme.typography.titleLarge)
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Switch(checked = pushOn, onCheckedChange = { pushOn = it })
            Text("放場推播通知")
        }
        Button(onClick = {
            scope.launch {
                WatchlistStore.setSports(ctx, sports)
                if (pushOn) WatchlistStore.grantPush(ctx)
            }
        }) { Text("儲存") }

        Spacer(Modifier.height(16.dp))
        Text("免責聲明", style = MaterialTheme.typography.titleMedium)
        Text(
            "資料來源：康文署 SmartPLAY 開放數據（每 2 分鐘鏡像）。餘額以官方 App 最終確認為準，本應用僅供參考。",
            style = MaterialTheme.typography.bodySmall
        )
    }
}