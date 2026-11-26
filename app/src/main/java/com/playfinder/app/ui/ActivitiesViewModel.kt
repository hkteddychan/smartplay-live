package com.playfinder.app.ui

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.playfinder.app.data.ActivityRepository
import com.playfinder.app.data.local.entity.ActivityEntity
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.time.LocalDate
import javax.inject.Inject

/** Date ranges offered for programme activities. */
enum class ActivityRange(val label: String, val days: Int?) {
    ALL("全部日期", null),
    WEEK("未來 7 日", 7),
    MONTH("未來 30 日", 30)
}

@OptIn(ExperimentalCoroutinesApi::class, FlowPreview::class)
@HiltViewModel
class ActivitiesViewModel @Inject constructor(
    private val repo: ActivityRepository
) : ViewModel() {

    private val _loading = MutableStateFlow(false)
    private val _error = MutableStateFlow<String?>(null)
    private val _district = MutableStateFlow("")
    private val _type = MutableStateFlow("")
    private val _search = MutableStateFlow("")
    private val _range = MutableStateFlow(ActivityRange.ALL)
    private val _lastSync = MutableStateFlow<Long?>(null)

    val loading: StateFlow<Boolean> = _loading.asStateFlow()
    val error: StateFlow<String?> = _error.asStateFlow()
    val district: StateFlow<String> = _district.asStateFlow()
    val type: StateFlow<String> = _type.asStateFlow()
    val search: StateFlow<String> = _search.asStateFlow()
    val range: StateFlow<ActivityRange> = _range.asStateFlow()
    val lastSync: StateFlow<Long?> = _lastSync.asStateFlow()

    private val allRows: StateFlow<List<ActivityEntity>> = repo.observeAll()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val districts: StateFlow<List<String>> = allRows
        .map { rows -> rows.map { it.district }.filter { it.isNotBlank() }.distinct().sorted() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val types: StateFlow<List<String>> = allRows
        .map { rows -> rows.map { it.type }.filter { it.isNotBlank() }.distinct().sorted() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    private val debouncedSearch: StateFlow<String> = _search
        .debounce(SEARCH_DEBOUNCE_MS)
        .stateIn(viewModelScope, SharingStarted.Eagerly, "")

    /** Room query re-runs whenever a filter changes; search is applied in memory. */
    val visible: StateFlow<List<ActivityEntity>> = combine(_district, _type, _range) { d, t, r ->
        Triple(d, t, r)
    }.flatMapLatest { (d, t, r) ->
        val today = LocalDate.now()
        val from = today.toString()
        val to = r.days?.let { today.plusDays((it - 1).toLong()).toString() } ?: "9999-12-31"
        repo.observe(d, t, from, to)
    }.combine(debouncedSearch) { rows, q ->
        if (q.isBlank()) rows
        else rows.filter { it.name.contains(q, true) || it.venue.contains(q, true) }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init {
        refresh()
    }

    fun setDistrict(d: String) {
        _district.value = d
    }

    fun setType(t: String) {
        _type.value = t
    }

    fun setSearch(q: String) {
        _search.value = q
    }

    fun setRange(r: ActivityRange) {
        _range.value = r
    }

    fun clearFilters() {
        _district.value = ""
        _type.value = ""
        _search.value = ""
        _range.value = ActivityRange.ALL
    }

    fun refresh() {
        if (_loading.value) return
        viewModelScope.launch {
            _loading.value = true
            _error.value = null
            runCatching { repo.refresh() }
                .onSuccess { _lastSync.value = System.currentTimeMillis() }
                .onFailure {
                    Log.w("ActivitiesViewModel", "refresh failed", it)
                    _error.value = "載入失敗，請檢查網絡連線"
                }
            _loading.value = false
        }
    }

    private companion object {
        const val SEARCH_DEBOUNCE_MS = 300L
    }
}
