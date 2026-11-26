package com.playfinder.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.playfinder.app.data.PlayFinderRepository
import com.playfinder.app.data.local.entity.SlotEntity
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val repo: PlayFinderRepository
) : ViewModel() {

    private val _slots = MutableStateFlow<List<SlotEntity>>(emptyList())
    val slots: StateFlow<List<SlotEntity>> = _slots

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    private var currentSport = "badminton"

    init {
        observe(currentSport)
        refresh()
    }

    fun selectSport(sport: String) {
        if (sport == currentSport) return
        currentSport = sport
        observe(sport)
        refresh()
    }

    private fun observe(sport: String) {
        viewModelScope.launch {
            repo.observeSlots(sport).collectLatest { _slots.value = it }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _loading.value = true
            _error.value = null
            runCatching { repo.refreshSport(currentSport) }
                .onFailure { _error.value = it.message ?: "載入失敗" }
            _loading.value = false
        }
    }
}