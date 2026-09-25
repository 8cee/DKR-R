package com.eightcee.dkrrecomp;

import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

final class ModInstaller {
    interface Callback {
        void onSuccess(File installedDirectory);
        void onFailure(String error);
    }

    private ModInstaller() {}

    static File installedDirectory(File modsRoot, JSONObject mod) throws Exception {
        String id = safeId(mod.getString("id"));
        String category = safeId(mod.optString("category", "gameplay"));
        return new File(new File(modsRoot, category), id);
    }

    static JSONObject installedMetadata(File modsRoot, JSONObject mod) {
        try {
            return readMetadata(new File(installedDirectory(modsRoot, mod), "mod.json"));
        } catch (Exception ignored) {
            return null;
        }
    }

    static JSONObject readMetadata(File metadata) {
        try {
            if (metadata == null || !metadata.isFile()) return null;
            try (FileInputStream in = new FileInputStream(metadata);
                 ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192];
                int n;
                while ((n = in.read(buffer)) > 0) {
                    if (out.size() + n > 1024 * 1024) return null;
                    out.write(buffer, 0, n);
                }
                return new JSONObject(new String(out.toByteArray(), StandardCharsets.UTF_8));
            }
        } catch (Exception ignored) {
            return null;
        }
    }

    static boolean remove(File modsRoot, JSONObject mod) {
        try {
            File destination = installedDirectory(modsRoot, mod);
            if (!destination.exists()) return true;
            deleteRecursive(destination);
            return !destination.exists();
        } catch (Exception e) {
            return false;
        }
    }

    static void install(File modsRoot, JSONObject mod, Callback callback) {
        new Thread(() -> {
            File tempZip = null;
            File staging = null;
            try {
                String id = safeId(mod.getString("id"));
                String category = safeId(mod.optString("category", "gameplay"));
                String url = mod.getString("downloadUrl");
                String expectedSha = mod.getString("sha256").toLowerCase(Locale.ROOT);
                if (!expectedSha.matches("[0-9a-f]{64}")) {
                    throw new IllegalArgumentException("Mod SHA-256 is missing or invalid.");
                }
                if (!url.startsWith("https://")) throw new IllegalArgumentException("Mod downloads must use HTTPS.");

                File categoryDir = new File(modsRoot, category);
                if (!categoryDir.exists() && !categoryDir.mkdirs()) throw new IllegalStateException("Could not create mod category.");
                tempZip = new File(categoryDir, "." + id + "-" + UUID.randomUUID() + ".zip");
                download(url, tempZip, mod.optLong("size", -1));

                String actual = sha256(tempZip);
                if (!actual.equals(expectedSha)) throw new SecurityException("SHA-256 verification failed.");

                staging = new File(categoryDir, "." + id + "-staging-" + UUID.randomUUID());
                if (!staging.mkdirs()) throw new IllegalStateException("Could not create staging directory.");
                unzipSafely(tempZip, staging);

                File packagedArchive = new File(staging, ".catalog-package.zip");
                copyFile(tempZip, packagedArchive);

                File metadata = new File(staging, "mod.json");
                try (FileOutputStream out = new FileOutputStream(metadata)) {
                    out.write(mod.toString(2).getBytes(StandardCharsets.UTF_8));
                    out.getFD().sync();
                }

                File destination = new File(categoryDir, id);
                File backup = new File(categoryDir, "." + id + "-previous");
                deleteRecursive(backup);
                if (destination.exists() && !destination.renameTo(backup)) {
                    throw new IllegalStateException("Could not preserve previous mod version.");
                }
                if (!staging.renameTo(destination)) {
                    if (backup.exists()) backup.renameTo(destination);
                    throw new IllegalStateException("Could not activate downloaded mod.");
                }
                deleteRecursive(backup);
                callback.onSuccess(destination);
            } catch (Exception e) {
                if (staging != null) deleteRecursive(staging);
                callback.onFailure(e.getMessage() == null ? e.toString() : e.getMessage());
            } finally {
                if (tempZip != null) tempZip.delete();
            }
        }, "DKR-ModInstaller").start();
    }

    private static void download(String source, File destination, long declaredSize) throws Exception {
        HttpURLConnection c = (HttpURLConnection)new URL(source).openConnection();
        c.setConnectTimeout(10000);
        c.setReadTimeout(30000);
        c.setInstanceFollowRedirects(true);
        c.setRequestProperty("User-Agent", "DKR-R-Android/" + BuildConfig.VERSION_NAME);
        if (c.getResponseCode() != 200) throw new IllegalStateException("Download HTTP " + c.getResponseCode());
        long contentLength = c.getContentLengthLong();
        if (contentLength > 512L * 1024L * 1024L) throw new SecurityException("Mod archive exceeds 512 MiB limit.");
        if (declaredSize >= 0 && contentLength >= 0 && declaredSize != contentLength) {
            throw new SecurityException("Mod archive size does not match catalog.");
        }
        try (BufferedInputStream in = new BufferedInputStream(c.getInputStream());
             FileOutputStream out = new FileOutputStream(destination)) {
            byte[] buffer = new byte[64 * 1024];
            long total = 0;
            int n;
            while ((n=in.read(buffer))>0) {
                total += n;
                if (total > 512L * 1024L * 1024L) throw new SecurityException("Mod archive exceeds 512 MiB limit.");
                out.write(buffer,0,n);
            }
            out.getFD().sync();
            if (declaredSize >= 0 && total != declaredSize) {
                throw new SecurityException("Downloaded size does not match catalog.");
            }
        } finally { c.disconnect(); }
    }

    private static void unzipSafely(File zip, File destination) throws Exception {
        String root = destination.getCanonicalPath() + File.separator;
        long expanded = 0;
        int files = 0;
        try (ZipInputStream zin = new ZipInputStream(new BufferedInputStream(new FileInputStream(zip)))) {
            ZipEntry entry;
            while ((entry=zin.getNextEntry())!=null) {
                if (++files > 10000) throw new SecurityException("Mod archive contains too many entries.");
                File out = new File(destination, entry.getName());
                String canonical = out.getCanonicalPath();
                if (!canonical.startsWith(root)) throw new SecurityException("Unsafe archive path rejected.");
                if (entry.isDirectory()) {
                    if (!out.exists() && !out.mkdirs()) throw new IllegalStateException("Could not create mod directory.");
                } else {
                    File parent=out.getParentFile();
                    if (parent!=null && !parent.exists() && !parent.mkdirs()) throw new IllegalStateException("Could not create mod directory.");
                    try (FileOutputStream fout=new FileOutputStream(out)) {
                        byte[] buffer=new byte[64*1024];
                        int n;
                        while ((n=zin.read(buffer))>0) {
                            expanded += n;
                            if (expanded > 1024L*1024L*1024L) throw new SecurityException("Expanded mod exceeds 1 GiB limit.");
                            fout.write(buffer,0,n);
                        }
                    }
                }
                zin.closeEntry();
            }
        }
    }

    static File packageArchive(File installedDirectory) {
        return new File(installedDirectory, ".catalog-package.zip");
    }

    static boolean recordActivation(File installedDirectory, String target, String nativeId) {
        try {
            File metadataFile = new File(installedDirectory, "mod.json");
            JSONObject metadata = readMetadata(metadataFile);
            if (metadata == null) return false;
            metadata.put("activatedTarget", target == null ? "library" : target);
            if (nativeId == null || nativeId.isEmpty()) metadata.remove("activatedNativeId");
            else metadata.put("activatedNativeId", nativeId);
            try (FileOutputStream out = new FileOutputStream(metadataFile)) {
                out.write(metadata.toString(2).getBytes(StandardCharsets.UTF_8));
                out.getFD().sync();
            }
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    private static void copyFile(File source, File destination) throws Exception {
        try (FileInputStream in = new FileInputStream(source);
             FileOutputStream out = new FileOutputStream(destination)) {
            byte[] buffer = new byte[64 * 1024];
            int n;
            while ((n = in.read(buffer)) > 0) out.write(buffer, 0, n);
            out.getFD().sync();
        }
    }

    static String sha256(File file) throws Exception {
        MessageDigest md=MessageDigest.getInstance("SHA-256");
        try (FileInputStream in=new FileInputStream(file)) {
            byte[] b=new byte[64*1024];
            int n;
            while ((n=in.read(b))>0) md.update(b,0,n);
        }
        StringBuilder s=new StringBuilder();
        for (byte x:md.digest()) s.append(String.format(Locale.ROOT,"%02x",x&255));
        return s.toString();
    }

    static String safeId(String value) {
        if (value == null || !value.matches("[a-z0-9][a-z0-9._-]{0,63}")) throw new IllegalArgumentException("Invalid mod identifier.");
        return value;
    }

    static void deleteRecursive(File file) {
        if (file == null || !file.exists()) return;
        if (file.isDirectory()) {
            File[] children=file.listFiles();
            if (children!=null) for (File child:children) deleteRecursive(child);
        }
        file.delete();
    }
}
