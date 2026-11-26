package com.playfinder.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.tooling.preview.Preview
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.playfinder.app.ui.HomeScreen
import com.playfinder.app.ui.SettingsScreen
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface {
                    PlayFinderNav()
                }
            }
        }
    }
}

@Composable
fun PlayFinderNav() {
    val HOME = "home"
    val FAVOURITES = "favourites"
    val ALERTS = "alerts"
    val ABOUT = "about"

    NavHost(navController = rememberNavController(), startDestination = HOME) {
        composable(HOME) { HomeScreen() }
        composable(FAVOURITES) { Text("我的收藏") }
        composable(ALERTS) { Text("放場通知") }
        composable(ABOUT) { SettingsScreen() }
    }
}

@Preview(showBackground = true)
@Composable
fun PlayFinderNavPreview() {
    MaterialTheme { PlayFinderNav() }
}