package com.zen2api

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.chaquo.python.Python

class ProxyService : Service() {

    companion object {
        const val CHANNEL_ID = "zen2api_proxy_channel"
        const val NOTIFICATION_ID = 1001
        const val ACTION_START = "com.zen2api.ACTION_START"
        const val ACTION_STOP = "com.zen2api.ACTION_STOP"
    }

    private var python: Python? = null
    private var isRunning = false

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        python = Python.getInstance()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: ACTION_START
        
        when (action) {
            ACTION_START -> {
                if (!isRunning) {
                    startPythonServices()
                    isRunning = true
                }
                val notification = buildNotification("Zen2API services running", "5 proxy services active")
                startForeground(NOTIFICATION_ID, notification)
            }
            ACTION_STOP -> {
                stopPythonServices()
                stopForeground(true)
                stopSelf()
            }
        }
        
        return START_STICKY
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Zen2API Proxy Services",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Running 5 AI proxy services in background"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(title: String, text: String): Notification {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setOnlyAlertOnce(true)
            .build()
    }

    private fun startPythonServices() {
        try {
            val module = python?.getModule("zen2api_main") ?: throw Exception("Module not found")
            val startFunc = module.getAttr("start_services")
            val result = startFunc.call()?.toBoolean() ?: false
            
            if (result) {
                Log.i("ProxyService", "Python services started successfully")
            } else {
                Log.e("ProxyService", "Python services failed to start")
            }
        } catch (e: Exception) {
            Log.e("ProxyService", "Start error", e)
        }
    }

    private fun stopPythonServices() {
        try {
            val module = python?.getModule("zen2api_main") ?: return
            val stopFunc = module.getAttr("stop_services")
            stopFunc.call()
            Log.i("ProxyService", "Python services stopped")
        } catch (e: Exception) {
            Log.e("ProxyService", "Stop error", e)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (isRunning) {
            stopPythonServices()
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null
}