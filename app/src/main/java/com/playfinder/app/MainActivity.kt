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
    const val HOME = "home"
    const val FAVOURITES = "favourites"
    const val ALERTS = "alerts"
    const val ABOUT = "about"

    NavHost(navController = rememberNavController(), startDestination = HOME) {
        composable(HOME) { Text("PlayFinder — 場地餘額") }
        composable(FAVOURITES) { Text("我的收藏") }
        composable(ALERTS) { Text("放場通知") }
        composable(ABOUT) { Text("關於 PlayFinder") }
    }
}

@Preview(showBackground = true)
@Composable
fun PlayFinderNavPreview() {
    MaterialTheme { PlayFinderNav() }
}