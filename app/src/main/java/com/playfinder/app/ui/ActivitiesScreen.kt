package com.playfinder.app.ui

import android.content.Intent
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import androidx.hilt.navigation.compose.hiltViewModel
import com.playfinder.app.data.local.entity.ActivityEntity

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ActivitiesScreen(vm: ActivitiesViewModel = hiltViewModel()) {
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()
    val district by vm.district.collectAsState()
    val type by vm.type.collectAsState()
    var districtOpen by remember { mutableStateOf(false) }
    var typeOpen by remember { mutableStateOf(false) }

    Scaffold(
        topBar = { TopAppBar(title = { Text("活動搜尋") }) },
        floatingActionButton = { FloatingActionButton(onClick = vm::refresh) { Text("↻") } }
    ) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            Row(
                Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box {
                    TextButton(onClick = { districtOpen = true }) {
                        Text(if (district.isBlank()) "全部地區 ▾" else "$district ▾")
                    }
                    DropdownMenu(expanded = districtOpen, onDismissRequest = { districtOpen = false }) {
                        DropdownMenuItem(text = { Text("全部地區") }, onClick = {
                            districtOpen = false; vm.setDistrict("")
                        })
                        vm.districts.forEach { d ->
                            DropdownMenuItem(text = { Text(d) }, onClick = {
                                districtOpen = false; vm.setDistrict(d)
                            })
                        }
                    }
                }
                Box {
                    TextButton(onClick = { typeOpen = true }) {
                        Text(if (type.isBlank()) "全部類型 ▾" else "$type ▾")
                    }
                    DropdownMenu(expanded = typeOpen, onDismissRequest = { typeOpen = false }) {
                        DropdownMenuItem(text = { Text("全部類型") }, onClick = {
                            typeOpen = false; vm.setType("")
                        })
                        vm.types.forEach { t ->
                            DropdownMenuItem(text = { Text(t) }, onClick = {
                                typeOpen = false; vm.setType(t)
                            })
                        }
                    }
                }
            }
            if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            error?.let {
                Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(8.dp))
            }
            if (!loading && vm.visible.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("暫無活動 — 撳 ↻ 重新載入")
                }
            } else {
                LazyColumn(Modifier.fillMaxSize()) {
                    items(vm.visible) { a -> ActivityRow(a) }
                }
            }
        }
    }
}

@Composable
private fun ActivityRow(a: ActivityEntity) {
    val ctx = LocalContext.current
    ListItem(
        headlineContent = { Text(a.name) },
        supportingContent = {
            Text(
                "${a.district} · ${a.type} · ${a.venue}\n" +
                    "${a.startDate} ${a.startTime}-${a.endTime} · 剩 ${a.placesLeft}/${a.quota} · " +
                    "費用 ${a.fee} · ${a.targetGroup}"
            )
        },
        trailingContent = {
            TextButton(onClick = {
                val i = Intent(Intent.ACTION_VIEW, a.url.toUri()).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                runCatching { ctx.startActivity(i) }
            }) { Text("報名") }
        }
    )
    HorizontalDivider()
}