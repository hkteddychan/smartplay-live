package com.playfinder.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.playfinder.app.data.local.dao.ActivityDao
import com.playfinder.app.data.local.dao.SlotDao
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val slotDao: SlotDao,
    private val activityDao: ActivityDao
) : ViewModel() {

    private val _clearing = MutableStateFlow(false)
    val clearing: StateFlow<Boolean> = _clearing.asStateFlow()

    val slotCount: StateFlow<Int> = slotDao.observeCount()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), 0)

    val activityCount: StateFlow<Int> = activityDao.observeCount()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), 0)

    /**
     * Clears cached rows through Room instead of deleting the open database
     * file (which could corrupt or re-create it underneath the connection).
     */
    fun clearCache(onResult: (Boolean) -> Unit) {
        if (_clearing.value) return
        viewModelScope.launch {
            _clearing.value = true
            val ok = runCatching {
                slotDao.clearAll()
                activityDao.clearAll()
            }.isSuccess
            _clearing.value = false
            onResult(ok)
        }
    }
}
