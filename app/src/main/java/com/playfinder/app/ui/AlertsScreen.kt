package com.playfinder.app.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.playfinder.app.ads.RewardedAdManager
import com.playfinder.app.alerts.Watchlist
import com.playfinder.app.alerts.WatchlistStore
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** The spec's reward gate: watch the ad, then stay in-app for three minutes. */
private const val GATE_SECONDS = 180

private enum class AdState { Idle, Loading, Counting }

/** ISO weekday number (1 = Monday) to the Chinese label. */
private val WEEKDAY_LABELS = listOf(1, 2, 3, 4, 5, 6, 7).zip(
    listOf("一", "二", "三", "四", "五", "六", "日")
)

private data class PushWindow(val label: String, val from: Int, val to: Int)

private val PUSH_WINDOWS = listOf(
    PushWindow("全日", 0, 24 * 60),
    PushWindow("早上 6–12", 6 * 60, 12 * 60),
    PushWindow("下午 12–18", 12 * 60, 18 * 60),
    PushWindow("黃昏 18–22", 18 * 60, 22 * 60),
    PushWindow("夜間 22–24", 22 * 60, 24 * 60)
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AlertsScreen() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }

    val wl by remember(ctx) { WatchlistStore.observe(ctx) }.collectAsState(initial = null)
    var adState by remember { mutableStateOf(AdState.Idle) }
    var remaining by remember { mutableIntStateOf(0) }
    var message by remember { mutableStateOf<String?>(null) }

    val notificationsGranted = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
        ContextCompat.checkSelfPermission(
            ctx, Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED

    val notificationPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        message = if (granted) "通知權限已開啟" else "未開啟通知權限，推播唔會顯示"
    }

    // 3-minute gate after the ad finishes. Leaving this screen cancels the
    // coroutine, so the grant is only issued if the user actually stays.
    LaunchedEffect(adState) {
        if (adState != AdState.Counting) return@LaunchedEffect
        remaining = GATE_SECONDS
        while (remaining > 0) {
            delay(1_000)
            remaining--
        }
        WatchlistStore.grantPush(ctx, weeks = 1)
        adState = AdState.Idle
        message = "已開通 1 星期推播 🎉"
        // The scope survives the state change that cancelled this effect.
        scope.launch { snackbar.showSnackbar("推播已開通，有效期 7 日") }
    }

    Scaffold(
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = { TopAppBar(title = { Text("通知") }) }
    ) { pad ->
        Column(
            Modifier
                .padding(pad)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            PushStatusCard(
                watchlist = wl,
                adState = adState,
                remaining = remaining,
                message = message,
                onWatchAd = {
                    val activity = ctx.findActivity()
                    if (activity == null) {
                        message = "無法開啟廣告，請稍後再試"
                        return@PushStatusCard
                    }
                    adState = AdState.Loading
                    message = null
                    scope.launch {
                        val earned = RewardedAdManager.showAndReward(activity)
                        if (earned) {
                            adState = AdState.Counting
                        } else {
                            adState = AdState.Idle
                            message = "未能完成廣告觀看，稍後再試"
                        }
                    }
                },
                onCancelGate = {
                    adState = AdState.Idle
                    message = "已取消，未開通推播"
                },
                onRevoke = {
                    scope.launch {
                        WatchlistStore.revokePush(ctx)
                        message = "已停止推播"
                    }
                }
            )

            if (!notificationsGranted) {
                NotificationPermissionCard(
                    onRequest = { notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS) }
                )
            }

            SportsCard(
                watchlist = wl,
                onToggle = { sport ->
                    scope.launch { WatchlistStore.toggleSport(ctx, sport) }
                }
            )

            WeekdayCard(
                watchlist = wl,
                onToggle = { day ->
                    scope.launch { WatchlistStore.toggleWeekday(ctx, day) }
                }
            )

            PushWindowCard(
                watchlist = wl,
                onSelect = { from, to ->
                    scope.launch { WatchlistStore.setTimeRange(ctx, from, to) }
                }
            )

            VenuesCard(
                watchlist = wl,
                onRemove = { venue ->
                    scope.launch { WatchlistStore.removeVenue(ctx, venue) }
                }
            )

            QuietHoursCard(
                watchlist = wl,
                onToggle = { enabled ->
                    scope.launch {
                        WatchlistStore.setQuietHours(
                            ctx,
                            if (enabled) 23 * 60 else -1,
                            if (enabled) 7 * 60 else -1
                        )
                    }
                }
            )

            DistrictsCard(
                watchlist = wl,
                onRemove = { district ->
                    scope.launch {
                        val current = wl?.districts.orEmpty()
                        WatchlistStore.setDistricts(ctx, current - district)
                    }
                }
            )

            Text(
                "推播只會喺偵測到場次餘額增加時發出，每個場次只通知一次。" +
                    "背景檢查每 15 分鐘一次（受 Android 省電設定影響）。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun PushStatusCard(
    watchlist: Watchlist?,
    adState: AdState,
    remaining: Int,
    message: String?,
    onWatchAd: () -> Unit,
    onCancelGate: () -> Unit,
    onRevoke: () -> Unit
) {
    val active = watchlist?.pushActive() == true
    val expiry = watchlist?.pushUntilEpoch ?: 0L

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Filled.Notifications,
                    contentDescription = null,
                    tint = if (active) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    }
                )
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f)) {
                    Text("放場推播", style = MaterialTheme.typography.titleMedium)
                    Text(
                        if (active) "有效至 ${formatDate(expiry)}" else "未啟用",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            when (adState) {
                AdState.Loading -> {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            strokeWidth = 2.dp
                        )
                        Spacer(Modifier.width(8.dp))
                        Text("載入廣告中…", style = MaterialTheme.typography.bodyMedium)
                    }
                }

                AdState.Counting -> {
                    val total = GATE_SECONDS
                    val progress = (total - remaining).toFloat() / total
                    Text(
                        "廣告已看完，請留在此頁 ${formatCountdown(remaining)} 以開通推播",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    LinearProgressIndicator(
                        progress = { progress },
                        modifier = Modifier.fillMaxWidth()
                    )
                    TextButton(onClick = onCancelGate) { Text("取消") }
                }

                AdState.Idle -> {
                    Button(
                        onClick = onWatchAd,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(if (active) "再睇廣告延長 1 星期" else "睇廣告 → 換 1 星期推播")
                    }
                }
            }

            message?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary
                )
            }

            if (active && adState == AdState.Idle) {
                TextButton(onClick = onRevoke) { Text("停止推播") }
            }
        }
    }
}

@Composable
private fun NotificationPermissionCard(onRequest: () -> Unit) {
    Card(
        Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
            contentColor = MaterialTheme.colorScheme.onErrorContainer
        )
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("通知權限未開啟", style = MaterialTheme.typography.titleSmall)
            Text(
                "Android 13 以上需要通知權限，否則推播唔會顯示。",
                style = MaterialTheme.typography.bodySmall
            )
            Button(onClick = onRequest) { Text("開啟通知權限") }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SportsCard(watchlist: Watchlist?, onToggle: (String) -> Unit) {
    val watched = watchlist?.sports.orEmpty()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("追蹤運動", style = MaterialTheme.typography.titleMedium)
            Text(
                "未揀選時預設追蹤羽毛球。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                SPORTS.forEach { (key, meta) ->
                    FilterChip(
                        selected = key in watched,
                        onClick = { onToggle(key) },
                        label = { Text("${meta.first} ${meta.second}") },
                        leadingIcon = if (key in watched) {
                            {
                                Icon(
                                    Icons.Filled.Check,
                                    contentDescription = null,
                                    modifier = Modifier.size(16.dp)
                                )
                            }
                        } else {
                            null
                        }
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun WeekdayCard(watchlist: Watchlist?, onToggle: (Int) -> Unit) {
    val days = watchlist?.weekdays.orEmpty()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("放場日子", style = MaterialTheme.typography.titleMedium)
            Text(
                if (days.isEmpty()) "未揀選 = 每一天" else "只會推播揀選嘅日子",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                WEEKDAY_LABELS.forEach { (iso, label) ->
                    FilterChip(
                        selected = iso in days,
                        onClick = { onToggle(iso) },
                        label = { Text("週$label") }
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PushWindowCard(watchlist: Watchlist?, onSelect: (Int, Int) -> Unit) {
    val from = watchlist?.fromMinute ?: 0
    val to = watchlist?.toMinute ?: (24 * 60)
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("放場時段", style = MaterialTheme.typography.titleMedium)
            Text(
                "只會推播呢個時間範圍內嘅場次。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                PUSH_WINDOWS.forEach { w ->
                    FilterChip(
                        selected = from == w.from && to == w.to,
                        onClick = { onSelect(w.from, w.to) },
                        label = { Text(w.label) }
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun VenuesCard(watchlist: Watchlist?, onRemove: (String) -> Unit) {
    val venues = watchlist?.venues.orEmpty()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("追蹤場地（最多 ${WatchlistStore.MAX_VENUES} 個）", style = MaterialTheme.typography.titleMedium)
            Text(
                if (venues.isEmpty()) {
                    "未設定 = 追蹤所有場地。喺場地列表長按任何場次即可加入該場地。"
                } else {
                    "已用 ${venues.size} / ${WatchlistStore.MAX_VENUES} 個。"
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (venues.isNotEmpty()) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    venues.sorted().forEach { v ->
                        InputChip(
                            selected = true,
                            onClick = { onRemove(v) },
                            label = { Text(v) },
                            trailingIcon = {
                                Icon(
                                    Icons.Filled.Close,
                                    contentDescription = "移除 $v",
                                    modifier = Modifier.size(16.dp)
                                )
                            }
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun QuietHoursCard(watchlist: Watchlist?, onToggle: (Boolean) -> Unit) {
    val enabled = watchlist?.quietHoursEnabled == true
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text("靜默時段（23:00–07:00）", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "靜默時段內唔會彈通知，但放場記錄會保留，到時段完結先提醒。",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Switch(checked = enabled, onCheckedChange = onToggle)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DistrictsCard(watchlist: Watchlist?, onRemove: (String) -> Unit) {
    val districts = watchlist?.districts.orEmpty()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("追蹤地區", style = MaterialTheme.typography.titleMedium)
            Text(
                "喺場地列表長按任何場次，即可加入該運動同地區。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (districts.isEmpty()) {
                Text(
                    "未設定（追蹤所有地區）",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            } else {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    districts.sorted().forEach { d ->
                        InputChip(
                            selected = true,
                            onClick = { onRemove(d) },
                            label = { Text(d) },
                            trailingIcon = {
                                Icon(
                                    Icons.Filled.Close,
                                    contentDescription = "移除 $d",
                                    modifier = Modifier.size(16.dp)
                                )
                            }
                        )
                    }
                }
            }
        }
    }
}

private fun formatDate(epoch: Long): String =
    SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault()).format(Date(epoch))

private fun formatCountdown(seconds: Int): String =
    "%d:%02d".format(seconds / 60, seconds % 60)
