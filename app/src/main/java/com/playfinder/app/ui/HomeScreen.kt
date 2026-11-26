package com.playfinder.app.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import com.playfinder.app.alerts.WatchlistStore
import com.playfinder.app.data.local.entity.SlotEntity
import kotlinx.coroutines.launch

val SPORTS = listOf(
    "badminton" to ("🏸" to "羽毛球"),
    "basketball" to ("🏀" to "籃球"),
    "volleyball" to ("🏐" to "排球"),
    "tennis" to ("🎾" to "網球"),
    "turf-soccer-pitch" to ("⚽" to "足球場")
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(vm: HomeViewModel = hiltViewModel()) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val filter by vm.filter.collectAsState()
    val sort by vm.sort.collectAsState()
    val sport by vm.sport.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()

    val locationPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { granted ->
        if (granted.values.any { it }) {
            com.google.android.gms.location.LocationServices
                .getFusedLocationProviderClient(ctx)
                .lastLocation
                .addOnSuccessListener { loc ->
                    if (loc != null) vm.setLocation(loc.latitude, loc.longitude)
                }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("PlayFinder — 場地餘額") },
                actions = {
                    IconButton(onClick = {
                        locationPermission.launch(
                            arrayOf(
                                Manifest.permission.ACCESS_FINE_LOCATION,
                                Manifest.permission.ACCESS_COARSE_LOCATION
                            )
                        )
                    }) { Text("📍") }
                }
            )
        },
        floatingActionButton = { FloatingActionButton(onClick = vm::refresh) { Text("↻") } }
    ) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            SportRow(selected = sport, onSelect = vm::selectSport)
            FilterBar(
                vm = vm,
                filter = filter,
                sort = sort,
                onSearch = { vm.setFilter(filter.copy(search = it)) },
                onDistrict = { vm.setFilter(filter.copy(district = it)) },
                onDate = { vm.setFilter(filter.copy(date = it)) },
                onOnlyAvailable = { vm.setFilter(filter.copy(onlyAvailable = it)) },
                onSort = vm::setSort
            )
            Heatmap(FilterEngine.heatmap(vm.visible))
            if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            error?.let {
                Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(8.dp))
            }
            if (!loading && vm.visible.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("暫無符合條件嘅場次")
                        TextButton(onClick = vm::refresh) { Text("重新載入") }
                    }
                }
            } else {
                LazyColumn(Modifier.fillMaxSize()) {
                    items(vm.visible) { s -> SlotRow(s) }
                }
            }
        }
    }
}

@Composable
private fun SportRow(selected: String, onSelect: (String) -> Unit) {
    Row(
        Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        SPORTS.forEach { (key, meta) ->
            FilterChip(
                selected = selected == key,
                onClick = { onSelect(key) },
                label = { Text("${meta.first} ${meta.second}") }
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FilterBar(
    vm: HomeViewModel,
    filter: SlotFilter,
    sort: SortMode,
    onSearch: (String) -> Unit,
    onDistrict: (String) -> Unit,
    onDate: (String) -> Unit,
    onOnlyAvailable: (Boolean) -> Unit,
    onSort: (SortMode) -> Unit
) {
    var districtOpen by remember { mutableStateOf(false) }
    var sortOpen by remember { mutableStateOf(false) }
    var search by remember { mutableStateOf(filter.search) }
    val dates = remember { (0..13).map { offset ->
        java.time.LocalDate.now().plusDays(offset.toLong()).toString()
    } }

    Column(Modifier.padding(horizontal = 8.dp)) {
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            OutlinedTextField(
                value = search,
                onValueChange = { search = it; onSearch(it) },
                label = { Text("場地名 / 設施") },
                singleLine = true,
                modifier = Modifier.weight(1f)
            )
            Spacer(Modifier.width(8.dp))
            Box {
                TextButton(onClick = { sortOpen = true }) {
                    Text(sortLabel(sort))
                }
                DropdownMenu(expanded = sortOpen, onDismissRequest = { sortOpen = false }) {
                    SortMode.entries.forEach { m ->
                        DropdownMenuItem(text = { Text(sortLabel(m)) }, onClick = {
                            sortOpen = false; onSort(m)
                        })
                    }
                }
            }
        }
        Row(
            Modifier.horizontalScroll(rememberScrollState()).padding(vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
        ) {
            Box {
                TextButton(onClick = { districtOpen = true }) {
                    Text(if (filter.district.isBlank()) "全部地區 ▾" else "${filter.district} ▾")
                }
                DropdownMenu(expanded = districtOpen, onDismissRequest = { districtOpen = false }) {
                    DropdownMenuItem(text = { Text("全部地區") }, onClick = {
                        districtOpen = false; onDistrict("")
                    })
                    vm.districts.forEach { d ->
                        DropdownMenuItem(text = { Text(d) }, onClick = {
                            districtOpen = false; onDistrict(d)
                        })
                    }
                }
            }
            FilterChip(
                selected = filter.date.isNotBlank(),
                onClick = { onDate("") },
                label = { Text("📅 全部日期") }
            )
            FilterChip(
                selected = filter.onlyAvailable,
                onClick = { onOnlyAvailable(!filter.onlyAvailable) },
                label = { Text("有餘額") }
            )
        }
        Row(
            Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            dates.take(7).forEach { d ->
                FilterChip(
                    selected = filter.date == d,
                    onClick = { onDate(if (filter.date == d) "" else d) },
                    label = { Text(d.substring(5)) }
                )
            }
        }
    }
}

private fun sortLabel(s: SortMode) = when (s) {
    SortMode.TIME -> "🕐 時間"
    SortMode.AVAILABILITY -> "🔢 餘額"
    SortMode.DISTANCE -> "📍 距離"
}

@Composable
private fun Heatmap(hours: IntArray) {
    val max = (hours.maxOrNull() ?: 0).coerceAtLeast(1)
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp)
    ) {
        hours.forEachIndexed { h, count ->
            val alpha = if (count == 0) 0.08f else 0.25f + 0.75f * (count.toFloat() / max)
            Box(
                Modifier
                    .weight(1f)
                    .height(24.dp)
                    .background(
                        MaterialTheme.colorScheme.primary.copy(alpha = alpha),
                        RoundedCornerShape(3.dp)
                    ),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    "$h",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurface
                )
            }
        }
    }
}

@Composable
private fun SlotRow(s: SlotEntity) {
    var menu by remember { mutableStateOf(false) }
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val color = if (s.available > 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
    val prime = FilterEngine.isPrimeTime(s.date, s.startTime)

    ListItem(
        headlineContent = {
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Text("${s.venue}")
                if (prime) {
                    Spacer(Modifier.width(6.dp))
                    Surface(
                        color = MaterialTheme.colorScheme.tertiary,
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Text(
                            "黄金時段",
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                        )
                    }
                }
            }
        },
        supportingContent = {
            Text("${s.district} · ${s.facility} ${s.location} · ${s.date} ${s.startTime}-${s.endTime}")
        },
        trailingContent = {
            Box {
                TextButton(onClick = { menu = true }) { Text("${s.available} 位", color = color) }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    DropdownMenuItem(text = { Text("watch 呢個場") }, onClick = {
                        menu = false
                        scope.launch { WatchlistStore.setSports(ctx, setOf(s.sport)) }
                    })
                    DropdownMenuItem(text = { Text("開官方網頁") }, onClick = {
                        menu = false
                        DeepLink.openInBrowser(ctx)
                    })
                    DropdownMenuItem(text = { Text("分享 WhatsApp") }, onClick = {
                        menu = false
                        val i = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(
                                android.content.Intent.EXTRA_TEXT,
                                "${s.venue} ${s.date} ${s.startTime}-${s.endTime} 餘 ${s.available}"
                            )
                        }
                        ctx.startActivity(android.content.Intent.createChooser(i, "分享"))
                    })
                }
            }
        }
    )
    HorizontalDivider()
}