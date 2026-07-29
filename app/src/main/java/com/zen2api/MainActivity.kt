package com.zen2api

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.chaquo.python.Python
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private var python: Python? = null
    private var isServicesRunning = false
    
    // UI elements
    private lateinit var tvStatus: TextView
    private lateinit var btnStart: Button
    private lateinit var btnStop: Button
    private lateinit var btnTest: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        // Initialize Chaquopy Python
        python = Python.getInstance()
        
        // Initialize UI
        tvStatus = findViewById(R.id.tvStatus)
        btnStart = findViewById(R.id.btnStart)
        btnStop = findViewById(R.id.btnStop)
        btnTest = findViewById(R.id.btnTest)
        
        setupListeners()
        checkServiceStatus()
        
        // Auto-start service
        startProxyService()
    }
    
    private fun setupListeners() {
        btnStart.setOnClickListener { startServices() }
        btnStop.setOnClickListener { stopServices() }
        btnTest.setOnClickListener { testEndpoints() }
    }
    
    private fun startProxyService() {
        val intent = Intent(this, ProxyService::class.java)
        intent.action = ProxyService.ACTION_START
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }
    
    private fun checkServiceStatus() {
        lifecycleScope.launch {
            try {
                val module = python?.getModule("zen2api_main")
                val serviceManager = module?.getAttr("service_manager")
                val running = serviceManager?.getAttr("running")?.toBoolean() ?: false
                
                runOnUiThread { updateUI(running) }
            } catch (e: Exception) {
                runOnUiThread { updateUI(false) }
            }
        }
    }
    
    private fun startServices() {
        btnStart.isEnabled = false
        tvStatus.text = "Starting services..."
        
        lifecycleScope.launch {
            try {
                val module = python?.getModule("zen2api_main") ?: throw Exception("Python module not loaded")
                val startFunc = module.getAttr("start_services")
                val result = startFunc.call()?.toBoolean() ?: false
                
                runOnUiThread {
                    if (result) {
                        tvStatus.text = "Services running on ports 9015, 18888, 9020, 9025, 9030"
                        btnStart.isEnabled = false
                        btnStop.isEnabled = true
                        isServicesRunning = true
                        Toast.makeText(this@MainActivity, "All 5 services started!", Toast.LENGTH_SHORT).show()
                    } else {
                        tvStatus.text = "Failed to start services"
                        btnStart.isEnabled = true
                        Toast.makeText(this@MainActivity, "Start failed", Toast.LENGTH_SHORT).show()
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    tvStatus.text = "Error: ${e.message}"
                    btnStart.isEnabled = true
                    Log.e("Zen2API", "Start error", e)
                    Toast.makeText(this@MainActivity, "Error: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }
    
    private fun stopServices() {
        btnStop.isEnabled = false
        tvStatus.text = "Stopping services..."
        
        lifecycleScope.launch {
            try {
                val module = python?.getModule("zen2api_main") ?: throw Exception("Python module not loaded")
                val stopFunc = module.getAttr("stop_services")
                stopFunc.call()
                
                runOnUiThread {
                    tvStatus.text = "Services stopped"
                    btnStart.isEnabled = true
                    btnStop.isEnabled = false
                    isServicesRunning = false
                    Toast.makeText(this@MainActivity, "Services stopped", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    tvStatus.text = "Error: ${e.message}"
                    btnStop.isEnabled = true
                    Log.e("Zen2API", "Stop error", e)
                    Toast.makeText(this@MainActivity, "Stop error: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }
    
    private fun testEndpoints() {
        btnTest.isEnabled = false
        tvStatus.text = "Testing endpoints..."
        
        lifecycleScope.launch {
            val endpoints = listOf(
                "zen2api" to "http://127.0.0.1:9015/health",
                "anyrouter" to "http://127.0.0.1:18888/health",
                "openrouter" to "http://127.0.0.1:9020/health",
                "codebuff" to "http://127.0.0.1:9025/health",
                "grok2api" to "http://127.0.0.1:9030/health"
            )
            
            val results = mutableListOf<String>()
            val client = okhttp3.OkHttpClient()
            
            for ((name, url) in endpoints) {
                try {
                    val request = okhttp3.Request.Builder().url(url).build()
                    val response = client.newCall(request).execute()
                    val body = response.body?.string()?.take(100) ?: ""
                    results.add("$name: ${response.code} $body")
                } catch (e: Exception) {
                    results.add("$name: ERROR - ${e.message}")
                }
            }
            
            runOnUiThread {
                tvStatus.text = results.joinToString("\n")
                btnTest.isEnabled = true
            }
        }
    }
    
    private fun updateUI(running: Boolean) {
        isServicesRunning = running
        btnStart.isEnabled = !running
        btnStop.isEnabled = running
        tvStatus.text = if (running) {
            "Services running on ports 9015, 18888, 9020, 9025, 9030"
        } else {
            "Services stopped - Tap Start to begin"
        }
    }
}