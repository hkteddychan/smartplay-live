package com.playfinder.app.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.playfinder.app.data.local.entity.SlotEntity

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(vm: HomeViewModel = hiltViewModel()) {
    val slots by vm.slots.collectAsState()
    val loading by vm.loading.collectAsState()

    Scaffold(
        topBar = { TopAppBar(title = { Text("PlayFinder — 場地餘額") }) }
    ) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            SportRow(selected = "badminton", onSelect = vm::selectSport)
            if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            LazyColumn(Modifier.fillMaxSize()) {
                items(slots) { s -> SlotRow(s) }
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
    ListItem(
        headlineContent = { Text("${s.venue} · ${s.facility}") },
        supportingContent = { Text("${s.date} ${s.startTime}-${s.endTime}") },
        trailingContent = { Text("${s.available} 位") }
    )
    HorizontalDivider()
}