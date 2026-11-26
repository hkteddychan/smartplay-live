package com.playfinder.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Info
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.playfinder.app.BuildConfig
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(vm: SettingsViewModel = hiltViewModel()) {
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }
    val clearing by vm.clearing.collectAsState()
    val slotCount by vm.slotCount.collectAsState()
    val activityCount by vm.activityCount.collectAsState()

    var confirmClear by remember { mutableStateOf(false) }

    Scaffold(
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = { TopAppBar(title = { Text("設定") }) }
    ) { pad ->
        Column(
            Modifier
                .padding(pad)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Filled.Info, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("關於 PlayFinder", style = MaterialTheme.typography.titleMedium)
                    }
                    Text(
                        "版本 ${BuildConfig.VERSION_NAME}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        "香港康文署場地餘額及康體活動搜尋。",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Text(
                        "本應用係第三方工具，與康文署並無關聯。",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("資料來源", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "康文署 SmartPLAY 開放數據（data.smartplay.lcsd.gov.hk），" +
                            "每 2 分鐘鏡像一次。",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Text(
                        "餘額以官方 App / 網站最終確認為準，本應用僅供參考。" +
                            "請於報名前自行核實場地及時間。",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("私隱", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "毋須註冊或登入，不收集個人資料。" +
                            "追蹤清單及推播設定只儲存在你的裝置（DataStore）。" +
                            "位置只用於計算距離排序，不會上傳。",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Text(
                        "完整私隱政策見專案內 PRIVACY.md。",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("離線快取", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "已快取 $slotCount 個場次、$activityCount 個活動。",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Text(
                        "清除後下次開啟需要重新下載。",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    OutlinedButton(
                        onClick = { confirmClear = true },
                        enabled = !clearing
                    ) {
                        if (clearing) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                strokeWidth = 2.dp
                            )
                            Spacer(Modifier.width(8.dp))
                        } else {
                            Icon(
                                Icons.Filled.Delete,
                                contentDescription = null,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(Modifier.width(8.dp))
                        }
                        Text("清除離線數據")
                    }
                }
            }

            Text(
                "推播設定請到「通知」分頁。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth()
            )
        }
    }

    if (confirmClear) {
        AlertDialog(
            onDismissRequest = { confirmClear = false },
            title = { Text("清除離線數據？") },
            text = { Text("已下載的場次及活動會被刪除，之後需要重新連線下載。追蹤清單及推播設定不受影響。") },
            confirmButton = {
                TextButton(onClick = {
                    confirmClear = false
                    vm.clearCache { ok ->
                        scope.launch {
                            snackbar.showSnackbar(if (ok) "快取已清除" else "清除失敗，請再試一次")
                        }
                    }
                }) { Text("清除") }
            },
            dismissButton = {
                TextButton(onClick = { confirmClear = false }) { Text("取消") }
            }
        )
    }
}
