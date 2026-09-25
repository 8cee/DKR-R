package com.eightcee.dkrrecomp;

import java.io.File;

final class CatalogModNative {
    private CatalogModNative() {}

    private static native String nativeActivate(String target, String archivePath, String filesDir);

    static String activate(File filesDir, File archive, String target) {
        if (target == null || target.equals("library")) return "OK\nStored in catalog library.";
        if (!BuildConfig.FULL_RUNTIME) {
            return "ERR\nThis package needs a full-runtime APK before it can be activated.";
        }
        if (archive == null || !archive.isFile()) return "ERR\nVerified package archive is missing.";
        return nativeActivate(target, archive.getAbsolutePath(), filesDir.getAbsolutePath());
    }
}
