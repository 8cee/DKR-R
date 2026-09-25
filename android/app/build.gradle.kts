plugins {
    id("com.android.application")
}

android {
    namespace = "com.eightcee.dkrrecomp"
    compileSdk = 35
    ndkVersion = "27.2.12479018"

    defaultConfig {
        applicationId = "com.eightcee.dkrrecomp"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }

        externalNativeBuild {
            cmake {
                cppFlags += listOf("-std=c++20", "-fexceptions", "-frtti")
                val hostFileToC = System.getenv("RT64_HOST_FILE_TO_C")
                if (!hostFileToC.isNullOrBlank()) {
                    arguments += "-DRT64_HOST_FILE_TO_C=$hostFileToC"
                }

                val fullRuntime = System.getenv("DKR_ANDROID_FULL_RUNTIME")
                if (fullRuntime == "1" || fullRuntime.equals("true", ignoreCase = true)) {
                    arguments += "-DDKR_ANDROID_FULL_RUNTIME=ON"
                    val generatedV77 = System.getenv("DKR_ANDROID_GENERATED_V77")
                    val generatedV80 = System.getenv("DKR_ANDROID_GENERATED_V80")
                    if (!generatedV77.isNullOrBlank()) {
                        arguments += "-DDKR_ANDROID_GENERATED_V77=$generatedV77"
                    }
                    if (!generatedV80.isNullOrBlank()) {
                        arguments += "-DDKR_ANDROID_GENERATED_V80=$generatedV80"
                    }
                }
            }
        }

        buildConfigField("String", "MOD_SERVER_URL", "\"https://raw.githubusercontent.com/8cee/DKR-R/android/android/mod-server/catalog.json\"")
    }

    buildFeatures {
        buildConfig = true
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
}
