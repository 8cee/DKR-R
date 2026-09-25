package com.eightcee.dkrrecomp;

import java.io.File;

final class CatalogModNative {
    static final class Result {
        final boolean ok;
        final String nativeId;
        final String message;

        Result(boolean ok, String nativeId, String message) {
            this.ok = ok;
            this.nativeId = nativeId == null ? "" : nativeId;
            this.message = message == null ? "" : message;
        }
    }

    private CatalogModNative() {}

    private static native String nativeActivate(String target, String archivePath, String filesDir, String expectedNativeId);
    private static native String nativeDeactivate(String target, String nativeId, String filesDir);

    static Result activate(File filesDir, File archive, String target, String expectedNativeId) {
        if (target == null || target.equals("library")) {
            return new Result(true, "", "Stored in catalog library.");
        }
        if (!BuildConfig.FULL_RUNTIME) {
            return new Result(false, "", "This package needs a full-runtime APK before it can be activated.");
        }
        if (archive == null || !archive.isFile()) {
            return new Result(false, "", "Verified package archive is missing.");
        }
        return parse(nativeActivate(target, archive.getAbsolutePath(), filesDir.getAbsolutePath(),
                expectedNativeId == null ? "" : expectedNativeId));
    }

    static Result deactivate(File filesDir, String target, String nativeId) {
        if (target == null || target.equals("library")) {
            return new Result(true, "", "Catalog library entry removed.");
        }
        if (!BuildConfig.FULL_RUNTIME) {
            return new Result(false, nativeId, "Native deactivation requires a full-runtime APK.");
        }
        if (nativeId == null || nativeId.isEmpty()) {
            return new Result(false, "", "Native activation identity is missing.");
        }
        return parse(nativeDeactivate(target, nativeId, filesDir.getAbsolutePath()));
    }

    private static Result parse(String raw) {
        if (raw == null) return new Result(false, "", "Native bridge returned no status.");
        String[] parts = raw.split("\n", 3);
        boolean ok = parts.length > 0 && parts[0].equals("OK");
        String id = parts.length > 1 ? parts[1] : "";
        String message = parts.length > 2 ? parts[2] : "";
        if (!ok && message.isEmpty() && parts.length > 1) message = parts[1];
        return new Result(ok, id, message);
    }
}
