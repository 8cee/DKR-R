package com.eightcee.dkrrecomp;

import android.content.Context;
import android.content.res.AssetManager;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

final class RuntimeAssets {
    private RuntimeAssets() {}

    static void ensureInstalled(Context context) throws Exception {
        File root = new File(context.getFilesDir(), "assets");
        File marker = new File(root, ".apk-assets-version");
        String version = installedVersion(context);

        if (marker.isFile()) {
            String current = new String(
                    Files.readAllBytes(marker.toPath()), StandardCharsets.UTF_8).trim();
            if (version.equals(current)) return;
        }

        File staging = new File(context.getFilesDir(), "assets.installing");
        deleteTree(staging);
        if (!staging.mkdirs() && !staging.isDirectory()) {
            throw new IllegalStateException("Could not create runtime asset staging directory.");
        }

        copyTree(context.getAssets(), "", staging);

        File backup = new File(context.getFilesDir(), "assets.previous");
        deleteTree(backup);
        if (root.exists() && !root.renameTo(backup)) {
            deleteTree(staging);
            throw new IllegalStateException("Could not rotate the previous runtime assets.");
        }
        if (!staging.renameTo(root)) {
            if (backup.exists()) backup.renameTo(root);
            deleteTree(staging);
            throw new IllegalStateException("Could not activate the packaged runtime assets.");
        }

        Files.write(marker.toPath(), (version + "\n").getBytes(StandardCharsets.UTF_8));
        deleteTree(backup);
    }

    private static String installedVersion(Context context)
            throws PackageManager.NameNotFoundException {
        PackageInfo info = context.getPackageManager().getPackageInfo(
                context.getPackageName(), 0);
        return Long.toString(info.lastUpdateTime);
    }

    private static void copyTree(AssetManager assets, String path, File destination)
            throws Exception {
        String[] children = assets.list(path);
        if (children != null && children.length > 0) {
            if (!destination.exists() && !destination.mkdirs()) {
                throw new IllegalStateException(
                        "Could not create runtime asset directory: " + destination);
            }
            for (String child : children) {
                String childPath = path.isEmpty() ? child : path + "/" + child;
                copyTree(assets, childPath, new File(destination, child));
            }
            return;
        }

        File parent = destination.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new IllegalStateException(
                    "Could not create runtime asset directory: " + parent);
        }
        try (InputStream input = assets.open(path);
             FileOutputStream output = new FileOutputStream(destination)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = input.read(buffer)) > 0) {
                output.write(buffer, 0, read);
            }
            output.getFD().sync();
        }
    }

    private static void deleteTree(File file) {
        if (file == null || !file.exists()) return;
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children != null) {
                for (File child : children) deleteTree(child);
            }
        }
        file.delete();
    }
}
