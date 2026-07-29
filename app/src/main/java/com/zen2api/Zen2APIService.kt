package com.zen2api

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.chaquo.python.Python

class Zen2APIService : Service() {
    companion object {
        const val CHANNEL_ID = "zen2api_service_channel"
        const val NOTIFICATION_ID = 1001
    }
    
    private var python: Python? = null
    
    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        python = Python.getInstance()
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = buildNotification()
        startForeground(NOTIFICATION_ID, notification)
        
        // Start Python services in background
        lifecycleScope.launch {
            startPythonServices()
        }
        
        return START_STICKY
    }
    
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Zen2API Services",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Running Zen2API proxy services in background"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }
    
    private fun buildNotification(): Notification {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Zen2API Android")
            .setContentText("Proxy services running: 9015, 18888, 9020, 9025, 9030")
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
    }
    
    private fun startPythonServices() {
        try {
            val module = python?.getModule("zen2api_main") ?: return
            val startFunc = module.getAttr("start_services")
            startFunc.call()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        try {
            val module = python?.getModule("zen2api_main") ?: return
            val stopFunc = module.getAttr("stop_services")
            stopFunc.call()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
    
    override fun onBind(intent: Intent?): IBinder? = null
}