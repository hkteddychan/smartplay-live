package com.playfinder.app.ui

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.playfinder.app.data.PlayFinderRepository
import com.playfinder.app.data.local.entity.SlotEntity
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
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
    private val _lastSync = MutableStateFlow<Long?>(null)

    private var observeJob: Job? = null

    val loading: StateFlow<Boolean> = _loading.asStateFlow()
    val error: StateFlow<String?> = _error.asStateFlow()
    val filter: StateFlow<SlotFilter> = _filter.asStateFlow()
    val sort: StateFlow<SortMode> = _sort.asStateFlow()
    val sport: StateFlow<String> = _sport.asStateFlow()
    val userLat: StateFlow<Double?> = _userLat.asStateFlow()
    val userLon: StateFlow<Double?> = _userLon.asStateFlow()
    val lastSync: StateFlow<Long?> = _lastSync.asStateFlow()

    /** Raw cached rows for the selected sport — drives empty vs no-results states. */
    val all: StateFlow<List<SlotEntity>> = _all.asStateFlow()

    val districts: StateFlow<List<String>> = _all
        .map { rows ->
            rows.map { it.district }
                .filter { it.isNotBlank() }
                .distinct()
                .sorted()
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    /**
     * Derived state, so Room writes and filter/sort changes both recompose the
     * list. Previously these were plain getters over a non-collected flow and
     * the UI stayed stale after the first render.
     */
    val visible: StateFlow<List<SlotEntity>> = combine(
        _all, _filter, _sort, _userLat, _userLon
    ) { all, filter, sort, lat, lon ->
        FilterEngine.sort(FilterEngine.apply(all, filter), sort, lat, lon)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val heatmap: StateFlow<IntArray> = visible
        .map { FilterEngine.heatmap(it) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), IntArray(24))

    init {
        observe(_sport.value)
        refresh()
    }

    fun selectSport(sport: String) {
        if (sport == _sport.value) return
        _sport.value = sport
        _all.value = emptyList()
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
        _sort.value = SortMode.DISTANCE
    }

    /** Tapping a heatmap bucket filters to that two-hour window (tap again to clear). */
    fun toggleHour(startHour: Int, endHour: Int) {
        val f = _filter.value
        val active = f.fromMinute == startHour * 60 && f.toMinute == endHour * 60
        _filter.value = if (active) {
            f.copy(fromMinute = 0, toMinute = 24 * 60)
        } else {
            f.copy(fromMinute = startHour * 60, toMinute = endHour * 60)
        }
    }

    fun clearFilters() {
        _filter.value = SlotFilter()
    }

    private fun observe(sport: String) {
        observeJob?.cancel()
        observeJob = viewModelScope.launch {
            repo.observeSlots(sport).collectLatest { _all.value = it }
        }
    }

    fun refresh() {
        if (_loading.value) return
        viewModelScope.launch {
            _loading.value = true
            _error.value = null
            runCatching { repo.refreshSport(_sport.value) }
                .onSuccess { _lastSync.value = System.currentTimeMillis() }
                .onFailure {
                    Log.w("HomeViewModel", "refresh failed for ${_sport.value}", it)
                    _error.value = "載入失敗，請檢查網絡連線"
                }
            _loading.value = false
        }
    }
}
