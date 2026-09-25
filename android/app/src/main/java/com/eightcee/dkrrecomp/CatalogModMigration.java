package com.eightcee.dkrrecomp;

import org.json.JSONObject;

import java.io.File;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

final class CatalogModMigration {
    private static final Set<String> OLD_CATEGORIES = new HashSet<>(Arrays.asList(
            "translations", "textures", "characters", "tracks", "gameplay", "ui"));

    private CatalogModMigration() {}

    static int migrate(File filesDir) {
        File oldRoot = new File(filesDir, "mods");
        File newRoot = new File(filesDir, "catalog-mods");
        if (!oldRoot.isDirectory()) return 0;

        int moved = 0;
        for (String category : OLD_CATEGORIES) {
            File oldCategory = new File(oldRoot, category);
            if (!oldCategory.isDirectory()) continue;

            File[] entries = oldCategory.listFiles(File::isDirectory);
            if (entries == null) continue;
            for (File candidate : entries) {
                JSONObject metadata = ModInstaller.readMetadata(new File(candidate, "mod.json"));
                if (!looksLikeCatalogInstall(metadata, category, candidate.getName())) continue;

                File destinationCategory = new File(newRoot, category);
                if (!destinationCategory.exists() && !destinationCategory.mkdirs()) continue;
                File destination = new File(destinationCategory, candidate.getName());
                if (destination.exists()) continue;

                if (candidate.renameTo(destination)) moved++;
            }

            File[] remaining = oldCategory.listFiles();
            if (remaining != null && remaining.length == 0) oldCategory.delete();
        }
        return moved;
    }

    private static boolean looksLikeCatalogInstall(JSONObject metadata, String category, String directoryName) {
        if (metadata == null) return false;
        try {
            String id = ModInstaller.safeId(metadata.getString("id"));
            String recordedCategory = ModInstaller.safeId(metadata.getString("category"));
            String downloadUrl = metadata.optString("downloadUrl", "");
            String sha256 = metadata.optString("sha256", "");
            return id.equals(directoryName) &&
                    recordedCategory.equals(category) &&
                    downloadUrl.startsWith("https://") &&
                    sha256.matches("(?i)[0-9a-f]{64}");
        } catch (Exception ignored) {
            return false;
        }
    }
}
