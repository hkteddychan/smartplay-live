package com.playfinder.app.ui

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import androidx.hilt.navigation.compose.hiltViewModel
import com.playfinder.app.R
import com.playfinder.app.data.local.entity.ActivityEntity
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private val HK = Locale.forLanguageTag("zh-Hant-HK")
private val ACT_DAY_FMT = DateTimeFormatter.ofPattern("M/d E", HK)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ActivitiesScreen(vm: ActivitiesViewModel = hiltViewModel()) {
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()
    val district by vm.district.collectAsState()
    val type by vm.type.collectAsState()
    val search by vm.search.collectAsState()
    val range by vm.range.collectAsState()
    val districts by vm.districts.collectAsState()
    val types by vm.types.collectAsState()
    val visible by vm.visible.collectAsState()
    val lastSync by vm.lastSync.collectAsState()

    var districtOpen by remember { mutableStateOf(false) }
    var typeOpen by remember { mutableStateOf(false) }
    var query by rememberSaveable { mutableStateOf(search) }
    LaunchedEffect(search) {
        if (search != query) query = search
    }

    Scaffold(
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            TopAppBar(
                title = { Text("康體活動") },
                actions = {
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
            OutlinedTextField(
                value = query,
                onValueChange = { query = it; vm.setSearch(it) },
                placeholder = { Text("搜尋活動名稱 / 場地") },
                leadingIcon = {
                    Icon(Icons.Filled.Search, contentDescription = null, modifier = Modifier.size(20.dp))
                },
                trailingIcon = {
                    if (query.isNotEmpty()) {
                        IconButton(onClick = { query = ""; vm.setSearch("") }) {
                            Icon(Icons.Filled.Close, contentDescription = "清除搜尋")
                        }
                    }
                },
                singleLine = true,
                shape = RoundedCornerShape(28.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 4.dp)
            )

            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Box(Modifier.weight(1f)) {
                    OutlinedButton(
                        onClick = { districtOpen = true },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(
                            if (district.isBlank()) "全部地區" else district,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    DropdownMenu(
                        expanded = districtOpen,
                        onDismissRequest = { districtOpen = false }
                    ) {
                        DropdownMenuItem(text = { Text("全部地區") }, onClick = {
                            districtOpen = false
                            vm.setDistrict("")
                        })
                        districts.forEach { d ->
                            DropdownMenuItem(text = { Text(d) }, onClick = {
                                districtOpen = false
                                vm.setDistrict(d)
                            })
                        }
                    }
                }
                Box(Modifier.weight(1f)) {
                    OutlinedButton(
                        onClick = { typeOpen = true },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(
                            if (type.isBlank()) "全部類型" else type,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    DropdownMenu(
                        expanded = typeOpen,
                        onDismissRequest = { typeOpen = false }
                    ) {
                        DropdownMenuItem(text = { Text("全部類型") }, onClick = {
                            typeOpen = false
                            vm.setType("")
                        })
                        types.forEach { t ->
                            DropdownMenuItem(text = { Text(t) }, onClick = {
                                typeOpen = false
                                vm.setType(t)
                            })
                        }
                    }
                }
            }

            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                ActivityRange.entries.forEach { r ->
                    FilterChip(
                        selected = range == r,
                        onClick = { vm.setRange(r) },
                        label = { Text(r.label) }
                    )
                }
            }

            if (lastSync != null) {
                Text(
                    "更新於 ${activityRelativeTime(lastSync!!)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 14.dp)
                )
            }

            Box(Modifier.weight(1f)) {
                when {
                    loading && visible.isEmpty() -> SkeletonActivityList()

                    error != null && visible.isEmpty() -> ActivityState(
                        title = error ?: stringResource(R.string.msg_load_failed),
                        body = "請確認網絡連線後重試。",
                        action = stringResource(R.string.action_retry),
                        onAction = vm::refresh
                    )

                    visible.isEmpty() -> ActivityState(
                        title = if (district.isBlank() && type.isBlank() && search.isBlank()) {
                            "暫無活動資料"
                        } else {
                            "冇符合條件嘅活動"
                        },
                        body = "試下清除篩選，或者遲啲再更新。",
                        action = "清除篩選",
                        onAction = vm::clearFilters
                    )

                    else -> PullToRefreshBox(
                        isRefreshing = loading,
                        onRefresh = vm::refresh,
                        modifier = Modifier.fillMaxSize()
                    ) {
                        LazyColumn(
                            Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(
                                start = 12.dp,
                                end = 12.dp,
                                top = 6.dp,
                                bottom = 88.dp
                            ),
                            verticalArrangement = Arrangement.spacedBy(10.dp)
                        ) {
                            items(visible, key = { it.id }) { activity ->
                                ActivityCard(activity)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ActivityCard(activity: ActivityEntity) {
    val ctx = LocalContext.current
    val available = activity.placesLeft > 0

    Card(
        Modifier
            .fillMaxWidth()
            .clickable {
                if (activity.url.isNotBlank()) {
                    val intent = Intent(Intent.ACTION_VIEW, activity.url.toUri()).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    runCatching { ctx.startActivity(intent) }
                }
            }
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    activity.name,
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
                Spacer(Modifier.width(8.dp))
                PlacesPill(available, activity.placesLeft, activity.quota)
            }

            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (activity.type.isNotBlank()) Tag(activity.type)
                if (activity.district.isNotBlank()) Tag(activity.district)
            }

            Text(
                "${formatActivityDate(activity.startDate)} · ${activity.startTime}–${activity.endTime}" +
                    if (activity.day.isNotBlank()) " · ${activity.day}" else "",
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold
            )

            if (activity.venue.isNotBlank()) {
                Text(
                    activity.venue,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )
            }

            if (activity.enrolStartDate.isNotBlank() || activity.enrolEndDate.isNotBlank()) {
                Text(
                    "報名日期：${activity.enrolStartDate.ifBlank { "—" }} – ${activity.enrolEndDate.ifBlank { "—" }}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    buildList {
                        add(if (activity.fee <= 0.0) "免費" else "$" + "%.0f".format(activity.fee))
                        if (activity.targetGroup.isNotBlank()) add(activity.targetGroup)
                        if (activity.enrolMethod.isNotBlank()) {
                            add(
                                when (activity.enrolMethod.uppercase(Locale.ROOT)) {
                                    "WALKIN" -> "即場報名"
                                    "ONLINE" -> "網上報名"
                                    else -> activity.enrolMethod
                                }
                            )
                        }
                    }.joinToString(" · "),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f)
                )
                if (activity.url.isNotBlank()) {
                    FilledTonalButton(
                        onClick = {
                            val intent = Intent(Intent.ACTION_VIEW, activity.url.toUri()).apply {
                                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            }
                            runCatching { ctx.startActivity(intent) }
                        }
                    ) { Text("報名") }
                }
            }
        }
    }
}

@Composable
private fun PlacesPill(available: Boolean, left: Int, quota: Int) {
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
                if (available) "$left/$quota" else "滿額",
                style = MaterialTheme.typography.labelMedium
            )
        }
    }
}

@Composable
private fun Tag(text: String) {
    Surface(
        color = MaterialTheme.colorScheme.secondaryContainer,
        contentColor = MaterialTheme.colorScheme.onSecondaryContainer,
        shape = RoundedCornerShape(50)
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
        )
    }
}

@Composable
private fun ActivityState(
    title: String,
    body: String,
    action: String,
    onAction: () -> Unit
) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(
            Modifier.padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(title, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
            Spacer(Modifier.height(6.dp))
            Text(
                body,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center
            )
            Spacer(Modifier.height(14.dp))
            Button(onClick = onAction) { Text(action) }
        }
    }
}

@Composable
private fun SkeletonActivityList() {
    Column(
        Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        repeat(4) {
            Card(Modifier.fillMaxWidth()) {
                Column(
                    Modifier.padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Box(
                        Modifier
                            .fillMaxWidth(0.7f)
                            .height(16.dp)
                            .background(
                                MaterialTheme.colorScheme.surfaceVariant,
                                RoundedCornerShape(4.dp)
                            )
                    )
                    Box(
                        Modifier
                            .fillMaxWidth(0.4f)
                            .height(10.dp)
                            .background(
                                MaterialTheme.colorScheme.surfaceVariant,
                                RoundedCornerShape(4.dp)
                            )
                    )
                    Box(
                        Modifier
                            .fillMaxWidth(0.9f)
                            .height(10.dp)
                            .background(
                                MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f),
                                RoundedCornerShape(4.dp)
                            )
                    )
                }
            }
        }
    }
}

private fun formatActivityDate(date: String): String = runCatching {
    LocalDate.parse(date).format(ACT_DAY_FMT)
}.getOrDefault(date)

private fun activityRelativeTime(epoch: Long): String {
    val minutes = ((System.currentTimeMillis() - epoch) / 60_000L).toInt()
    return when {
        minutes < 1 -> "啱啱"
        minutes < 60 -> "$minutes 分鐘前"
        else -> DateTimeFormatter.ofPattern("HH:mm", Locale.getDefault())
            .format(java.time.Instant.ofEpochMilli(epoch).atZone(java.time.ZoneId.systemDefault()))
    }
}
