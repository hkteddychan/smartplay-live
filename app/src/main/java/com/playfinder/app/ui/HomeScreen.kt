package com.playfinder.app.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.unit.dp
import androidx.compose.ui.platform.LocalContext
import androidx.hilt.navigation.compose.hiltViewModel
import com.playfinder.app.alerts.WatchlistStore
import com.playfinder.app.data.local.entity.SlotEntity
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(vm: HomeViewModel = hiltViewModel()) {
    val slots by vm.slots.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()

    Scaffold(
        topBar = { TopAppBar(title = { Text("PlayFinder — 場地餘額") }) },
        floatingActionButton = {
            FloatingActionButton(onClick = vm::refresh) { Text("↻") }
        }
    ) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            SportRow(selected = "badminton", onSelect = vm::selectSport)
            if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(8.dp)) }
            if (!loading && slots.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("暫無場地數據 — 撳 ↻ 重新載入")
                }
            } else {
                LazyColumn(Modifier.fillMaxSize()) {
                    items(slots) { s -> SlotRow(s) }
                }
            }
        }
    }
}

@Composable
private fun SportRow(selected: String, onSelect: (String) -> Unit) {
    val sports = listOf("badminton" to "🏸", "basketball" to "🏀", "volleyball" to "🏐", "tennis" to "🎾", "turf-soccer-pitch" to "⚽")
    Row(Modifier.horizontalScroll(rememberScrollState()).padding(8.dp)) {
        sports.forEach { (k, icon) ->
            FilterChip(
                selected = selected == k,
                onClick = { onSelect(k) },
                label = { Text(icon) },
                modifier = Modifier.padding(end = 6.dp)
            )
        }
    }
}

@Composable
private fun SlotRow(s: SlotEntity) {
    var menu by remember { mutableStateOf(false) }
    val ctx = LocalContext.current
    val color = when {
        s.available > 0 -> MaterialTheme.colorScheme.primary
        else -> MaterialTheme.colorScheme.error
    }
    ListItem(
        headlineContent = { Text("${s.venue} · ${s.facility}") },
        supportingContent = { Text("${s.date} ${s.startTime}-${s.endTime}") },
        trailingContent = {
            Box {
                TextButton(onClick = { menu = true }) { Text("${s.available} 位", color = color) }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    DropdownMenuItem(text = { Text("watch 呢個場") }, onClick = {
                        menu = false
                        kotlinx.coroutines.MainScope().launch {
                            WatchlistStore.setSports(ctx, setOf(s.sport))
                        }
                    })
                    DropdownMenuItem(text = { Text("開官方網頁") }, onClick = {
                        menu = false
                        DeepLink.openInBrowser(ctx)
                    })
                    DropdownMenuItem(text = { Text("分享 WhatsApp") }, onClick = {
                        menu = false
                        val i = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(android.content.Intent.EXTRA_TEXT, "${s.venue} ${s.date} ${s.startTime}-${s.endTime} 餘 ${s.available}")
                        }
                        ctx.startActivity(android.content.Intent.createChooser(i, "分享"))
                    })
                }
            }
        }
    )
    HorizontalDivider()
}