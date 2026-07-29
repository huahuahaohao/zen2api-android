#!/usr/bin/env bash
# Build script for Zen2API Android APK
# Usage: ./build_apk.sh

set -e

PROJECT_DIR="/root/zen2api_android"
BUILD_DIR="$PROJECT_DIR/build"

echo "======================================"
echo "Building Zen2API Android APK"
echo "======================================"

# Check for Android SDK
if [ -z "$ANDROID_HOME" ] && [ -z "$ANDROID_SDK_ROOT" ]; then
    echo "ERROR: ANDROID_HOME or ANDROID_SDK_ROOT not set"
    echo "Please install Android SDK and set environment variable"
    exit 1
fi

# Check for gradle
if ! command -v gradle &> /dev/null; then
    echo "Gradle not found, using wrapper..."
    if [ ! -f "$PROJECT_DIR/gradlew" ]; then
        echo "Generating gradle wrapper..."
        cd "$PROJECT_DIR" && gradle wrapper --gradle-version 8.5
    fi
    GRADLE_CMD="$PROJECT_DIR/gradlew"
else
    GRADLE_CMD="gradle"
fi

cd "$PROJECT_DIR"

# Clean previous builds
echo "Cleaning..."
$GRADLE_CMD clean

# Build debug APK
echo "Building debug APK..."
$GRADLE_CMD assembleDebug

# Find the APK
APK_PATH=$(find "$PROJECT_DIR" -name "*.apk" -path "*/outputs/apk/*" | head -1)

if [ -n "$APK_PATH" ]; then
    echo ""
    echo "======================================"
    echo "Build successful!"
    echo "APK location: $APK_PATH"
    echo "Size: $(du -h "$APK_PATH" | cut -f1)"
    echo "======================================"
    
    # Copy to accessible location
    cp "$APK_PATH" "/root/zen2api_android.apk"
    echo "Copied to: /root/zen2api_android.apk"
else
    echo "ERROR: APK not found after build"
    exit 1
fi