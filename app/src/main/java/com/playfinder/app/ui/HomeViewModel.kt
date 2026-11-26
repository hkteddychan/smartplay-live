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

    private var currentSport = "badminton"

    init { observe(currentSport) }

    fun selectSport(sport: String) {
        if (sport == currentSport) return
        currentSport = sport
        observe(sport)
    }

    private fun observe(sport: String) {
        viewModelScope.launch {
            repo.observeSlots(sport).collectLatest { _slots.value = it }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _loading.value = true
            runCatching { repo.refreshSport(currentSport) }
            _loading.value = false
        }
    }
}