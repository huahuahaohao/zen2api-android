package com.zen2api

import android.app.Application
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

class Zen2APIApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        
        // Initialize Chaquopy Python
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
            Log.d("Zen2API", "Python initialized")
        }
        
        // Pre-load the zen2api module
        try {
            val python = Python.getInstance()
            python.getModule("zen2api_main")
            Log.d("Zen2API", "zen2api_main module preloaded")
        } catch (e: Exception) {
            Log.w("Zen2API", "Module preload failed (expected on first run): ${e.message}")
        }
    }
}