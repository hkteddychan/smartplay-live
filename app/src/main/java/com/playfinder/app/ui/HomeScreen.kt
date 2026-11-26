package com.playfinder.app.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import com.playfinder.app.R
import com.playfinder.app.alerts.WatchlistStore
import com.playfinder.app.core.FilterEngine
import com.playfinder.app.core.SlotFilter
import com.playfinder.app.core.SortMode
import com.playfinder.app.data.local.entity.SlotEntity
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

val SPORTS = listOf(
    "badminton" to ("🏸" to "羽毛球"),
    "basketball" to ("🏀" to "籃球"),
    "volleyball" to ("🏐" to "排球"),
    "tennis" to ("🎾" to "網球"),
    "turf-soccer-pitch" to ("⚽" to "足球場")
)

private val HK = Locale.forLanguageTag("zh-Hant-HK")
private val DAY_FMT = DateTimeFormatter.ofPattern("M/d E", HK)
private val TIME_FMT = DateTimeFormatter.ofPattern("HH:mm", Locale.getDefault())

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(vm: HomeViewModel = hiltViewModel()) {
    val ctx = LocalContext.current
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    val filter by vm.filter.collectAsState()
    val sort by vm.sort.collectAsState()
    val sport by vm.sport.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()
    val all by vm.all.collectAsState()
    val visible by vm.visible.collectAsState()
    val heatmap by vm.heatmap.collectAsState()
    val districts by vm.districts.collectAsState()
    val availableDates by vm.availableDates.collectAsState()
    val lastSync by vm.lastSync.collectAsState()

    var showFilters by rememberSaveable { mutableStateOf(false) }

    val locationPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { granted ->
        if (granted.values.any { it }) {
            @Suppress("MissingPermission")
            com.google.android.gms.location.LocationServices
                .getFusedLocationProviderClient(ctx)
                .lastLocation
                .addOnSuccessListener { loc ->
                    if (loc != null) vm.setLocation(loc.latitude, loc.longitude)
                }
        }
    }

    Scaffold(
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = {
            TopAppBar(
                title = { Text("場地餘額") },
                actions = {
                    IconButton(onClick = {
                        val fine = ContextCompat.checkSelfPermission(
                            ctx, Manifest.permission.ACCESS_FINE_LOCATION
                        ) == PackageManager.PERMISSION_GRANTED
                        if (fine) {
                            locationPermission.launch(
                                arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
                            )
                        } else {
                            locationPermission.launch(
                                arrayOf(
                                    Manifest.permission.ACCESS_FINE_LOCATION,
                                    Manifest.permission.ACCESS_COARSE_LOCATION
                                )
                            )
                        }
                    }) {
                        Icon(
                            Icons.Filled.Place,
                            contentDescription = stringResource(R.string.cd_locate)
                        )
                    }
                    IconButton(onClick = vm::refresh, enabled = !loading) {
                        if (loading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                strokeWidth = 2.dp
                            )
                        } else {
                            Icon(
                                Icons.Filled.Refresh,
                                contentDescription = stringResource(R.string.cd_refresh)
                            )
                        }
                    }
                }
            )
        }
    ) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            SportRow(selected = sport, onSelect = vm::selectSport)

            FilterSummaryRow(
                search = filter.search,
                activeCount = activeFilterCount(filter),
                onSearch = vm::setSearch,
                onOpenFilters = { showFilters = true }
            )

            if (activeFilterCount(filter) > 0) {
                ActiveFilterChips(
                    filter = filter,
                    onFilter = vm::setFilter
                )
            }

            HeatmapCard(
                hours = heatmap,
                filter = filter,
                onToggleHour = vm::toggleHour
            )

            SyncBanner(
                lastSync = lastSync,
                error = error,
                hasData = all.isNotEmpty(),
                onRetry = vm::refresh
            )

            Box(Modifier.weight(1f)) {
                when {
                    loading && all.isEmpty() -> SkeletonList()

                    error != null && all.isEmpty() -> StateMessage(
                        title = error ?: stringResource(R.string.msg_load_failed),
                        body = stringResource(R.string.msg_not_synced_body),
                        action = stringResource(R.string.action_retry),
                        onAction = vm::refresh
                    )

                    all.isEmpty() -> StateMessage(
                        title = stringResource(R.string.msg_not_synced),
                        body = stringResource(R.string.msg_not_synced_body),
                        action = stringResource(R.string.action_reload),
                        onAction = vm::refresh
                    )

                    visible.isEmpty() -> StateMessage(
                        title = stringResource(R.string.msg_no_results),
                        body = stringResource(R.string.msg_no_results_body),
                        action = stringResource(R.string.action_clear_filters),
                        onAction = vm::clearFilters
                    )

                    else -> PullToRefreshBox(
                        isRefreshing = loading,
                        onRefresh = vm::refresh,
                        modifier = Modifier.fillMaxSize()
                    ) {
                        LazyColumn(
                            Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(bottom = 88.dp)
                        ) {
                            items(visible, key = { it.id }) { slot ->
                                SlotRow(
                                    slot = slot,
                                    onWatch = {
                                        scope.launch {
                                            WatchlistStore.addSport(ctx, slot.sport)
                                            WatchlistStore.addDistrict(ctx, slot.district)
                                            val venueAdded = WatchlistStore.addVenue(ctx, slot.venue)
                                            snackbar.showSnackbar(
                                                if (venueAdded) {
                                                    "已加入追蹤：${slot.venue}"
                                                } else {
                                                    "已追蹤 ${slot.sport}／${slot.district}；場地追蹤已達上限 ${WatchlistStore.MAX_VENUES} 個"
                                                }
                                            )
                                        }
                                    }
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    if (showFilters) {
        FilterSheet(
            filter = filter,
            sort = sort,
            districts = districts,
            dates = availableDates,
            onFilter = vm::setFilter,
            onSort = vm::setSort,
            onDismiss = { showFilters = false }
        )
    }
}

private fun activeFilterCount(f: SlotFilter): Int {
    var n = 0
    if (f.district.isNotBlank()) n++
    if (f.date.isNotBlank()) n++
    if (f.fromMinute != 0 || f.toMinute != 24 * 60) n++
    if (f.onlyAvailable) n++
    return n
}

@Composable
private fun SportRow(selected: String, onSelect: (String) -> Unit) {
    LazyRow(
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        items(SPORTS) { (key, meta) ->
            FilterChip(
                selected = selected == key,
                onClick = { onSelect(key) },
                label = { Text("${meta.first} ${meta.second}") }
            )
        }
    }
}

@Composable
private fun FilterSummaryRow(
    search: String,
    activeCount: Int,
    onSearch: (String) -> Unit,
    onOpenFilters: () -> Unit
) {
    var query by rememberSaveable { mutableStateOf(search) }
    LaunchedEffect(search) {
        if (search != query) query = search
    }

    Row(
        Modifier.fillMaxWidth().padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        OutlinedTextField(
            value = query,
            onValueChange = { query = it; onSearch(it) },
            placeholder = { Text("搜尋場地名 / 設施") },
            leadingIcon = {
                Icon(Icons.Filled.Search, contentDescription = null, modifier = Modifier.size(20.dp))
            },
            trailingIcon = {
                if (query.isNotEmpty()) {
                    IconButton(onClick = { query = ""; onSearch("") }) {
                        Icon(Icons.Filled.Close, contentDescription = "清除搜尋")
                    }
                }
            },
            singleLine = true,
            shape = RoundedCornerShape(28.dp),
            modifier = Modifier.weight(1f)
        )
        Spacer(Modifier.width(8.dp))
        BadgedBox(
            badge = {
                if (activeCount > 0) Badge { Text("$activeCount") }
            }
        ) {
            FilledTonalButton(onClick = onOpenFilters) {
                Text(stringResource(R.string.filter_title))
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ActiveFilterChips(filter: SlotFilter, onFilter: (SlotFilter) -> Unit) {
    val chips = buildList {
        if (filter.district.isNotBlank()) {
            add(filter.district to { onFilter(filter.copy(district = "")) })
        }
        if (filter.date.isNotBlank()) {
            add(
                labelForDate(filter.date) to { onFilter(filter.copy(date = "")) }
            )
        }
        if (filter.fromMinute != 0 || filter.toMinute != 24 * 60) {
            add(
                "${filter.fromMinute / 60}:00–${filter.toMinute / 60}:00" to {
                    onFilter(filter.copy(fromMinute = 0, toMinute = 24 * 60))
                }
            )
        }
        if (filter.onlyAvailable) {
            add("有餘額" to { onFilter(filter.copy(onlyAvailable = false)) })
        }
    }
    FlowRow(
        Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        chips.forEach { (label, remove) ->
            InputChip(
                selected = true,
                onClick = remove,
                label = { Text(label) },
                trailingIcon = {
                    Icon(Icons.Filled.Close, contentDescription = "移除", modifier = Modifier.size(16.dp))
                }
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun FilterSheet(
    filter: SlotFilter,
    sort: SortMode,
    districts: List<String>,
    dates: List<String>,
    onFilter: (SlotFilter) -> Unit,
    onSort: (SortMode) -> Unit,
    onDismiss: () -> Unit
) {
    var districtOpen by remember { mutableStateOf(false) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text("篩選", style = MaterialTheme.typography.titleLarge)

            SectionLabel("地區")
            Box {
                OutlinedButton(onClick = { districtOpen = true }, modifier = Modifier.fillMaxWidth()) {
                    Text(
                        if (filter.district.isBlank()) "全部地區" else filter.district,
                        modifier = Modifier.weight(1f),
                        textAlign = TextAlign.Start
                    )
                }
                DropdownMenu(
                    expanded = districtOpen,
                    onDismissRequest = { districtOpen = false }
                ) {
                    DropdownMenuItem(text = { Text("全部地區") }, onClick = {
                        districtOpen = false
                        onFilter(filter.copy(district = ""))
                    })
                    districts.forEach { d ->
                        DropdownMenuItem(text = { Text(d) }, onClick = {
                            districtOpen = false
                            onFilter(filter.copy(district = d))
                        })
                    }
                }
            }

            SectionLabel("日期")
            LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                item {
                    FilterChip(
                        selected = filter.date.isBlank(),
                        onClick = { onFilter(filter.copy(date = "")) },
                        label = { Text("全部") }
                    )
                }
                items(dates) { d ->
                    FilterChip(
                        selected = filter.date == d,
                        onClick = {
                            onFilter(filter.copy(date = if (filter.date == d) "" else d))
                        },
                        label = { Text(labelForDate(d)) }
                    )
                }
            }

            SectionLabel("時段")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                TIME_RANGES.forEach { (label, from, to) ->
                    val selected = filter.fromMinute == from * 60 && filter.toMinute == to * 60
                    FilterChip(
                        selected = selected,
                        onClick = {
                            onFilter(
                                if (selected) filter.copy(fromMinute = 0, toMinute = 24 * 60)
                                else filter.copy(fromMinute = from * 60, toMinute = to * 60)
                            )
                        },
                        label = { Text(label) }
                    )
                }
            }

            SectionLabel("排序")
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                SortMode.entries.forEachIndexed { index, mode ->
                    SegmentedButton(
                        selected = sort == mode,
                        onClick = { onSort(mode) },
                        shape = SegmentedButtonDefaults.itemShape(index, SortMode.entries.size),
                        label = { Text(sortLabel(mode)) }
                    )
                }
            }

            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text("只顯示有餘額", style = MaterialTheme.typography.bodyLarge)
                    Text(
                        "隱藏已滿嘅時段",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Switch(
                    checked = filter.onlyAvailable,
                    onCheckedChange = { onFilter(filter.copy(onlyAvailable = it)) }
                )
            }

            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                OutlinedButton(
                    onClick = { onFilter(SlotFilter()); onSort(SortMode.TIME) },
                    modifier = Modifier.weight(1f)
                ) { Text("重設") }
                Button(onClick = onDismiss, modifier = Modifier.weight(1f)) { Text("完成") }
            }
        }
    }
}

private val TIME_RANGES = listOf(
    Triple("全日", 0, 24),
    Triple("早上 6–12", 6, 12),
    Triple("下午 12–18", 12, 18),
    Triple("黄昏 18–22", 18, 22),
    Triple("夜間 22–24", 22, 24)
)

@Composable
private fun SectionLabel(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.titleSmall,
        color = MaterialTheme.colorScheme.primary
    )
}

@Composable
private fun HeatmapCard(
    hours: IntArray,
    filter: SlotFilter,
    onToggleHour: (Int, Int) -> Unit
) {
    val buckets = remember(hours) {
        (0 until 12).map { i ->
            i to ((hours.getOrNull(i * 2) ?: 0) + (hours.getOrNull(i * 2 + 1) ?: 0))
        }
    }
    val max = (buckets.maxOfOrNull { it.second } ?: 0).coerceAtLeast(1)

    Card(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 6.dp)
    ) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("時段空位", style = MaterialTheme.typography.titleSmall)
                Spacer(Modifier.weight(1f))
                Text("少", style = MaterialTheme.typography.labelSmall)
                Spacer(Modifier.width(4.dp))
                listOf(0.15f, 0.4f, 0.65f, 0.9f).forEach { a ->
                    Box(
                        Modifier
                            .padding(horizontal = 1.dp)
                            .size(10.dp)
                            .clip(RoundedCornerShape(2.dp))
                            .background(MaterialTheme.colorScheme.primary.copy(alpha = a))
                    )
                }
                Spacer(Modifier.width(4.dp))
                Text("多", style = MaterialTheme.typography.labelSmall)
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                buckets.forEach { (i, count) ->
                    val start = i * 2
                    val end = start + 2
                    val selected =
                        filter.fromMinute == start * 60 && filter.toMinute == end * 60
                    val alpha = if (count == 0) 0.06f else 0.25f + 0.75f * (count.toFloat() / max)
                    val cd = stringResource(R.string.cd_heatmap_cell, start, end, count)
                    val base = Modifier
                        .weight(1f)
                        .height(40.dp)
                        .clip(RoundedCornerShape(4.dp))
                        .background(MaterialTheme.colorScheme.primary.copy(alpha = alpha))
                    Box(
                        modifier = (if (selected) {
                            base.border(
                                2.dp,
                                MaterialTheme.colorScheme.onSurface,
                                RoundedCornerShape(4.dp)
                            )
                        } else {
                            base
                        })
                            .clickable { onToggleHour(start, end) }
                            .semantics { contentDescription = cd },
                        contentAlignment = Alignment.Center
                    ) {
                        if (i % 3 == 0) {
                            Text(
                                "$start",
                                style = MaterialTheme.typography.labelSmall,
                                color = if (alpha > 0.55f) {
                                    MaterialTheme.colorScheme.onPrimary
                                } else {
                                    MaterialTheme.colorScheme.onSurfaceVariant
                                }
                            )
                        }
                    }
                }
            }
            Spacer(Modifier.height(4.dp))
            Text(
                "撳一格即可篩選該兩小時時段",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@Composable
private fun SyncBanner(
    lastSync: Long?,
    error: String?,
    hasData: Boolean,
    onRetry: () -> Unit
) {
    if (error != null && hasData) {
        Surface(
            color = MaterialTheme.colorScheme.errorContainer,
            contentColor = MaterialTheme.colorScheme.onErrorContainer,
            shape = RoundedCornerShape(8.dp),
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 2.dp)
        ) {
            Row(
                Modifier.padding(start = 10.dp, top = 4.dp, bottom = 4.dp, end = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    Icons.Filled.Warning,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp)
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    stringResource(R.string.msg_offline),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.weight(1f)
                )
                TextButton(onClick = onRetry) { Text(stringResource(R.string.action_retry)) }
            }
        }
    } else if (lastSync != null) {
        Text(
            "更新於 ${relativeTime(lastSync)}",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 2.dp)
        )
    }
}

private fun relativeTime(epoch: Long): String {
    val minutes = ((System.currentTimeMillis() - epoch) / 60_000L).toInt()
    return when {
        minutes < 1 -> "啱啱"
        minutes < 60 -> "$minutes 分鐘前"
        else -> TIME_FMT.format(Instant.ofEpochMilli(epoch).atZone(ZoneId.systemDefault()))
    }
}

@Composable
private fun StateMessage(
    title: String,
    body: String?,
    action: String,
    onAction: () -> Unit
) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(
            Modifier.padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(title, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
            if (body != null) {
                Spacer(Modifier.height(6.dp))
                Text(
                    body,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    textAlign = TextAlign.Center
                )
            }
            Spacer(Modifier.height(14.dp))
            Button(onClick = onAction) { Text(action) }
        }
    }
}

@Composable
private fun SkeletonList() {
    Column(
        Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        repeat(6) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(
                    Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Box(
                        Modifier
                            .fillMaxWidth(0.55f)
                            .height(14.dp)
                            .clip(RoundedCornerShape(4.dp))
                            .background(MaterialTheme.colorScheme.surfaceVariant)
                    )
                    Box(
                        Modifier
                            .fillMaxWidth(0.8f)
                            .height(10.dp)
                            .clip(RoundedCornerShape(4.dp))
                            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f))
                    )
                }
                Spacer(Modifier.width(12.dp))
                Box(
                    Modifier
                        .size(52.dp, 24.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(MaterialTheme.colorScheme.surfaceVariant)
                )
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun SlotRow(slot: SlotEntity, onWatch: () -> Unit) {
    var menu by remember { mutableStateOf(false) }
    val ctx = LocalContext.current
    val available = slot.available > 0
    val prime = FilterEngine.isPrimeTime(slot.date, slot.startTime)

    ListItem(
        modifier = Modifier
            .minimumInteractiveComponentSize()
            .combinedClickable(
                onClick = { menu = true },
                onLongClick = onWatch
            ),
        headlineContent = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    slot.venue,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false)
                )
                if (prime) {
                    Spacer(Modifier.width(6.dp))
                    Surface(
                        color = MaterialTheme.colorScheme.tertiaryContainer,
                        contentColor = MaterialTheme.colorScheme.onTertiaryContainer,
                        shape = RoundedCornerShape(4.dp)
                    ) {
                        Text(
                            "黄金時段",
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
            }
        },
        supportingContent = {
            Column {
                Text(
                    "${slot.date} · ${slot.startTime}–${slot.endTime}",
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold
                )
                Text(
                    listOf(slot.district, slot.facility, slot.location)
                        .filter { it.isNotBlank() }
                        .joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )
            }
        },
        trailingContent = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                AvailabilityPill(available = available, count = slot.available)
                Box {
                    IconButton(onClick = { menu = true }) {
                        Icon(
                            Icons.Filled.MoreVert,
                            contentDescription = stringResource(R.string.cd_more)
                        )
                    }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        DropdownMenuItem(
                            text = { Text("追蹤此運動及地區") },
                            onClick = { menu = false; onWatch() }
                        )
                        DropdownMenuItem(
                            text = { Text("開官方網頁") },
                            onClick = { menu = false; DeepLink.openInBrowser(ctx) }
                        )
                        DropdownMenuItem(
                            text = { Text("分享到 WhatsApp / Telegram") },
                            onClick = {
                                menu = false
                                val share = Intent(Intent.ACTION_SEND).apply {
                                    type = "text/plain"
                                    putExtra(
                                        Intent.EXTRA_TEXT,
                                        "${slot.venue} ${slot.date} ${slot.startTime}-${slot.endTime} 餘 ${slot.available} 位"
                                    )
                                }
                                ctx.startActivity(Intent.createChooser(share, "分享"))
                            }
                        )
                    }
                }
            }
        }
    )
    HorizontalDivider()
}

@Composable
private fun AvailabilityPill(available: Boolean, count: Int) {
    Surface(
        color = if (available) {
            MaterialTheme.colorScheme.primaryContainer
        } else {
            MaterialTheme.colorScheme.errorContainer
        },
        contentColor = if (available) {
            MaterialTheme.colorScheme.onPrimaryContainer
        } else {
            MaterialTheme.colorScheme.onErrorContainer
        },
        shape = RoundedCornerShape(50)
    ) {
        Row(
            Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                if (available) Icons.Filled.Check else Icons.Filled.Close,
                contentDescription = if (available) {
                    stringResource(R.string.cd_available)
                } else {
                    stringResource(R.string.cd_full)
                },
                modifier = Modifier.size(14.dp)
            )
            Spacer(Modifier.width(4.dp))
            Text(
                if (available) "$count 位" else "滿額",
                style = MaterialTheme.typography.labelMedium
            )
        }
    }
}

private fun sortLabel(mode: SortMode) = when (mode) {
    SortMode.TIME -> "時間"
    SortMode.AVAILABILITY -> "餘額"
    SortMode.DISTANCE -> "距離"
}

private fun labelForDate(date: String): String = runCatching {
    LocalDate.parse(date).format(DAY_FMT)
}.getOrDefault(date)
