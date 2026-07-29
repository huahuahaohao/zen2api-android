# Zen2API Android App

Android client for Zen2API - runs 5 proxy services on your phone:
1. **zen2api** (port 9015) - OpenAI/Anthropic format proxy to Zen upstream
2. **anyrouter** (port 18888) - Anthropic-compatible proxy to AnyRouter
3. **openrouter** (port 9020) - OpenRouter free-model proxy
4. **codebuff** (port 9025) - Codebuff free-model proxy
5. **grok2api** (port 9030) - Grok/NVIDIA/Modal/Kilo proxies

Built with Chaquopy (Python 3.10) + Kotlin + FastAPI/uvicorn.

---

## Quick Build (x86_64 host)

```bash
# Prerequisites: JDK 17, Android SDK (cmdline-tools + build-tools 34.0.0 + platform 34)
export ANDROID_HOME=/path/to/android-sdk
export JAVA_HOME=/path/to/jdk-17

./gradlew assembleDebug --no-daemon
# APK at: app/build/outputs/apk/debug/app-debug.apk
```

---

## GitHub Actions (Auto-build on tag)

```bash
git tag v1.0.0
git push origin v1.0.0
```

Workflow downloads artifacts:
- `zen2api-android-x86_64-debug.apk` (from ubuntu-latest runner)

For ARM64 APK, add a **self-hosted ARM64 runner** (your server/phone) and uncomment the `build-arm64` job in `.github/workflows/android.yml`.

---

## Project Structure

```
zen2api_android/
├── app/
│   ├── src/main/
│   │   ├── java/com/zen2api/
│   │   │   ├── MainActivity.kt           # UI
│   │   │   ├── ProxyService.kt           # Foreground service
│   │   │   ├── Zen2APIApplication.kt     # App init
│   │   │   ├── Zen2APIService.kt         # Service manager
│   │   │   └── BootReceiver.kt           # Auto-start on boot
│   │   ├── python/zen2api_main.py        # 5 FastAPI services
│   │   ├── AndroidManifest.xml
│   │   └── res/
│   └── build.gradle                      # Chaquopy 12.x config
├── build.gradle                          # Root: AGP 8.4, KGP 1.9.20, Chaquopy 12.0.0
├── gradle.properties                     # android.useAndroidX=true
├── gradlew / gradle/wrapper/             # Gradle 8.5 wrapper
├── settings.gradle
└── .github/workflows/android.yml         # CI workflow
```

---

## Configuration (via Android app UI or env)

| Service | Env Var | Required |
|---------|---------|----------|
| zen2api | `ZEN2API_KEY` | Yes |
| anyrouter | `ANYROUTER_API_KEY` | Yes |
| openrouter | `OPENROUTER_API_KEYS` (comma-separated) | Yes |
| codebuff | `CODEBUFF_AUTH_TOKEN` | Yes |
| grok2api | `NVIDIA_API_KEYS`, `MODAL_TOKENS` (comma-separated) | Optional |

Set in app Settings screen, or via `adb shell am broadcast -a com.zen2api.CONFIG --es ZEN2API_KEY "sk-..."`

---

## Run on Device

1. Install APK: `adb install app-debug.apk`
2. Open app → grant "Display over other apps" + "Battery optimization off"
3. Tap **Start Services** → 5 ports listen on `0.0.0.0`
4. Test: `curl http://<phone-ip>:9015/health`

---

## Notes

- **Chaquopy 12.x** requires Python config OUTSIDE `defaultConfig` block (fixed in `app/build.gradle`)
- **Min SDK 24** (Android 7.0), **Target SDK 34**
- **ABIs**: `armeabi-v7a`, `arm64-v8a`, `x86`, `x86_64` (NDK filters)
- **Python 3.10** bundled (Chaquopy downloads prebuilt)
- **Gradle 8.5**, **AGP 8.4**, **Kotlin 1.9.20**