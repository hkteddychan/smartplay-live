package com.playfinder.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.playfinder.app.data.PlayFinderRepository
import com.playfinder.app.data.local.entity.SlotEntity
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val repo: PlayFinderRepository
) : ViewModel() {

    private val _all = MutableStateFlow<List<SlotEntity>>(emptyList())
    private val _loading = MutableStateFlow(false)
    private val _error = MutableStateFlow<String?>(null)
    private val _filter = MutableStateFlow(SlotFilter())
    private val _sort = MutableStateFlow(SortMode.TIME)
    private val _sport = MutableStateFlow("badminton")
    private val _userLat = MutableStateFlow<Double?>(null)
    private val _userLon = MutableStateFlow<Double?>(null)

    val loading: StateFlow<Boolean> = _loading.asStateFlow()
    val error: StateFlow<String?> = _error.asStateFlow()
    val filter: StateFlow<SlotFilter> = _filter.asStateFlow()
    val sort: StateFlow<SortMode> = _sort.asStateFlow()
    val sport: StateFlow<String> = _sport.asStateFlow()

    init {
        observe(_sport.value)
        refresh()
    }

    val districts: List<String>
        get() = _all.value.map { it.district }.filter { it.isNotBlank() }.distinct().sorted()

    val visible: List<SlotEntity>
        get() = FilterEngine.sort(
            FilterEngine.apply(_all.value, _filter.value),
            _sort.value,
            _userLat.value,
            _userLon.value
        )

    val heatmap: IntArray get() = FilterEngine.heatmap(visible)

    fun selectSport(sport: String) {
        if (sport == _sport.value) return
        _sport.value = sport
        observe(sport)
        refresh()
    }

    fun setFilter(f: SlotFilter) {
        _filter.value = f
    }

    fun setSort(mode: SortMode) {
        _sort.value = mode
    }

    fun setLocation(lat: Double, lon: Double) {
        _userLat.value = lat
        _userLon.value = lon
    }

    private fun observe(sport: String) {
        viewModelScope.launch {
            repo.observeSlots(sport).collectLatest { _all.value = it }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _loading.value = true
            _error.value = null
            runCatching { repo.refreshSport(_sport.value) }
                .onFailure { _error.value = it.message ?: "載入失敗" }
            _loading.value = false
        }
    }
}