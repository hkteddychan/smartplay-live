package com.playfinder.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.playfinder.app.ui.ActivitiesScreen
import com.playfinder.app.ui.AlertsScreen
import com.playfinder.app.ui.HomeScreen
import com.playfinder.app.ui.SettingsScreen
import com.playfinder.app.ui.theme.PlayFinderTheme
import dagger.hilt.android.AndroidEntryPoint

private object Routes {
    const val HOME = "home"
    const val ACTIVITIES = "activities"
    const val ALERTS = "alerts"
    const val SETTINGS = "settings"
}

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val TABS = listOf(
    Tab(Routes.HOME, "場地", Icons.Filled.Home),
    Tab(Routes.ACTIVITIES, "活動", Icons.Filled.DateRange),
    Tab(Routes.ALERTS, "通知", Icons.Filled.Notifications),
    Tab(Routes.SETTINGS, "設定", Icons.Filled.Settings)
)

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent {
            PlayFinderTheme {
                AppShell()
            }
        }
    }
}

@Composable
fun AppShell() {
    val nav = rememberNavController()
    val backStack by nav.currentBackStackEntryAsState()
    val current = backStack?.destination

    Scaffold(
        // Insets are handled by each screen's TopAppBar and the NavigationBar,
        // so the shell must not add another layer of system-bar padding.
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            NavigationBar {
                TABS.forEach { tab ->
                    NavigationBarItem(
                        selected = current?.hierarchy?.any { it.route == tab.route } == true,
                        onClick = {
                            nav.navigate(tab.route) {
                                popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(tab.icon, contentDescription = null) },
                        label = { Text(tab.label) }
                    )
                }
            }
        }
    ) { pad ->
        NavHost(
            navController = nav,
            startDestination = Routes.HOME,
            modifier = Modifier.padding(pad)
        ) {
            composable(Routes.HOME) { HomeScreen() }
            composable(Routes.ACTIVITIES) { ActivitiesScreen() }
            composable(Routes.ALERTS) { AlertsScreen() }
            composable(Routes.SETTINGS) { SettingsScreen() }
        }
    }
}
