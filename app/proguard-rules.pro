# PlayFinder R8 / ProGuard rules.
#
# The release build enables minify + resource shrinking, so anything reached
# only by reflection must be kept explicitly.

# Retrofit keeps generic signatures and annotations at runtime.
-keepattributes Signature, InnerClasses, EnclosingMethod
-keepattributes RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations
-keepattributes AnnotationDefault

# Retrofit service interfaces are implemented by a runtime proxy.
-if interface * { @retrofit2.http.* <methods>; }
-keep,allowobfuscation interface <1>
-keep,allowobfuscation,allowshrinking interface retrofit2.Call
-keep,allowobfuscation,allowshrinking class retrofit2.Response

# OkHttp / Okio optional platform hooks.
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# Moshi generated adapters are looked up by name from the @JsonClass type.
-keep class com.playfinder.app.data.remote.dto.** { *; }
-keepclassmembers class com.playfinder.app.data.remote.dto.** {
    <init>(...);
    <fields>;
}
-keep class kotlin.Metadata { *; }
-keepclassmembers class kotlin.Metadata {
    public <methods>;
}

# Enum valueOf / values are used by Room and the filter engine.
-keepclassmembers enum * {
    public static **[] values();
    public static ** valueOf(java.lang.String);
}

# WorkManager instantiates workers by name through the Hilt worker factory.
-keep class * extends androidx.work.ListenableWorker { <init>(...); }

# Room generated implementations.
-keep class * extends androidx.room.RoomDatabase { <init>(); }
