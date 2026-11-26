package com.playfinder.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.playfinder.app.ads.RewardedAdManager
import com.playfinder.app.alerts.WatchlistStore
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val wl by WatchlistStore.observe(ctx).collectAsState(initial = null)
    var adRunning by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }

    Scaffold(topBar = { TopAppBar(title = { Text("設定 / 通知") }) }) { pad ->
        Column(
            Modifier.padding(pad).verticalScroll(rememberScrollState()).padding(16.dp).fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text("放場推播", style = MaterialTheme.typography.titleMedium)
            val expiry = wl?.pushUntilEpoch ?: 0L
            val active = wl?.pushEnabled == true && expiry > System.currentTimeMillis()
            Text(
                if (active) "推播有效至 ${formatDate(expiry)}" else "推播未啟用",
                style = MaterialTheme.typography.bodyMedium
            )

            Button(
                enabled = !adRunning,
                onClick = {
                    adRunning = true
                    scope.launch {
                        val earned = RewardedAdManager.showAndReward(ctx as android.app.Activity)
                        if (earned) {
                            WatchlistStore.grantPush(ctx, 1)
                            message = "已開通 1 星期推播 🎉"
                        } else {
                            message = "未能完成廣告觀看，稍後再試"
                        }
                        adRunning = false
                    }
                }
            ) { Text(if (adRunning) "載入廣告中…" else "睇 3 分鐘廣告 → 換 1 星期推播") }

            message?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }

            HorizontalDivider()
            Text("追蹤項目", style = MaterialTheme.typography.titleMedium)
            Text(
                "已追蹤運動：" + (wl?.sports?.joinToString("、")?.takeIf { it.isNotBlank() } ?: "（未設定）"),
                style = MaterialTheme.typography.bodyMedium
            )
            Text(
                "已追蹤地區：" + (wl?.districts?.joinToString("、")?.takeIf { it.isNotBlank() } ?: "（全部）"),
                style = MaterialTheme.typography.bodyMedium
            )

            HorizontalDivider()
            Text("清除快取", style = MaterialTheme.typography.titleMedium)
            OutlinedButton(onClick = {
                scope.launch {
                    ctx.deleteDatabase("playfinder.db")
                    message = "快取已清除"
                }
            }) { Text("清除離線數據") }

            HorizontalDivider()
            Text("關於 / 免責聲明", style = MaterialTheme.typography.titleMedium)
            Text(
                "PlayFinder 係第三方應用，與康文署並無關聯。\n\n" +
                    "資料來源：LCSD SmartPLAY 開放數據（每 2 分鐘鏡像）。\n" +
                    "餘額以官方 App 最終確認為準，本應用僅供參考。\n\n" +
                    "本應用不收集任何個人資料；收藏清單只儲存在你的裝置本機。\n" +
                    "推播經由 ntfy（ntfy.tedton.hk）以匿名方式發送。",
                style = MaterialTheme.typography.bodySmall
            )
            Text(
                "Privacy Policy / 私隱政策：見專案內 PRIVACY.md",
                style = MaterialTheme.typography.labelSmall,
                textAlign = TextAlign.Start
            )
        }
    }
}

private fun formatDate(epoch: Long): String =
    SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault()).format(Date(epoch))