package com.playfinder.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.playfinder.app.data.ActivityRepository
import com.playfinder.app.data.local.entity.ActivityEntity
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ActivitiesViewModel @Inject constructor(
    private val repo: ActivityRepository
) : ViewModel() {

    private val _all = MutableStateFlow<List<ActivityEntity>>(emptyList())
    private val _loading = MutableStateFlow(false)
    private val _error = MutableStateFlow<String?>(null)
    private val _district = MutableStateFlow("")
    private val _type = MutableStateFlow("")
    private val _from = MutableStateFlow(java.time.LocalDate.now().toString())

    val loading: StateFlow<Boolean> = _loading.asStateFlow()
    val error: StateFlow<String?> = _error.asStateFlow()
    val district: StateFlow<String> = _district.asStateFlow()
    val type: StateFlow<String> = _type.asStateFlow()

    init { refresh() }

    val districts: List<String>
        get() = _all.value.map { it.district }.filter { it.isNotBlank() }.distinct().sorted()

    val types: List<String>
        get() = _all.value.map { it.type }.filter { it.isNotBlank() }.distinct().sorted()

    val visible: List<ActivityEntity>
        get() = _all.value.filter { a ->
            (_district.value.isBlank() || a.district == _district.value) &&
                (_type.value.isBlank() || a.type == _type.value) &&
                a.startDate >= _from.value
        }

    fun setDistrict(d: String) { _district.value = d }
    fun setType(t: String) { _type.value = t }
    fun setFrom(d: String) { _from.value = d }

    fun refresh() {
        viewModelScope.launch {
            _loading.value = true
            _error.value = null
            runCatching { repo.refresh() }.onFailure { _error.value = it.message ?: "載入失敗" }
            _loading.value = false
        }
    }
}