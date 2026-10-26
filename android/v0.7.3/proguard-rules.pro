# LibVLC uses JNI and reflection to bind its Java bridge.
-keep class org.videolan.** { *; }
-dontwarn org.videolan.**
-keep class fi.iki.elonen.** { *; }
