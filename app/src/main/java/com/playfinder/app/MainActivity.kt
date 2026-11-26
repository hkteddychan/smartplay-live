package com.playfinder.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.compose.*
import com.playfinder.app.ui.ActivitiesScreen
import com.playfinder.app.ui.HomeScreen
import com.playfinder.app.ui.SettingsScreen
import dagger.hilt.android.AndroidEntryPoint

private object Routes {
    const val HOME = "home"
    const val ACTIVITIES = "activities"
    const val ALERTS = "alerts"
    const val ABOUT = "about"
}

private data class Tab(val route: String, val label: String, val icon: String)

private val TABS = listOf(
    Tab(Routes.HOME, "場地", "🏸"),
    Tab(Routes.ACTIVITIES, "活動", "🏊"),
    Tab(Routes.ALERTS, "通知", "🔔"),
    Tab(Routes.ABOUT, "設定", "⚙️")
)

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme { AppShell() } }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppShell() {
    val nav = rememberNavController()
    val backStack by nav.currentBackStackEntryAsState()
    val current = backStack?.destination

    Scaffold(
        bottomBar = {
            NavigationBar {
                TABS.forEach { tab ->
                    NavigationBarItem(
                        selected = current?.hierarchy?.any { it.route == tab.route } == true,
                        onClick = {
                            nav.navigate(tab.route) {
                                popUpTo(Routes.HOME) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Text(tab.icon) },
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
            composable(Routes.ALERTS) { SettingsScreen() }
            composable(Routes.ABOUT) { SettingsScreen() }
        }
    }
}

@Preview(showBackground = true)
@Composable
fun AppShellPreview() { MaterialTheme { AppShell() } }