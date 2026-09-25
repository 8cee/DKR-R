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
