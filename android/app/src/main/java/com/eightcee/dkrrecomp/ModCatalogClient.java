package com.eightcee.dkrrecomp;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

final class ModCatalogClient {
    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();
    private static final int SUPPORTED_SCHEMA = 1;
    private static final int MAX_CATALOG_BYTES = 2 * 1024 * 1024;

    private ModCatalogClient() {}

    static void fetchCatalog(String catalogUrl, Consumer<JSONObject> success, Consumer<String> failure) {
        EXECUTOR.execute(() -> {
            HttpURLConnection connection = null;
            try {
                if (catalogUrl == null || !catalogUrl.startsWith("https://")) {
                    throw new IllegalArgumentException("Mod catalog must use HTTPS.");
                }
                connection = (HttpURLConnection) new URL(catalogUrl).openConnection();
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(12000);
                connection.setInstanceFollowRedirects(true);
                connection.setRequestProperty("Accept", "application/json");
                connection.setRequestProperty("User-Agent", "DKR-R-Android/" + BuildConfig.VERSION_NAME);
                int code = connection.getResponseCode();
                if (code != 200) throw new IllegalStateException("Mod server HTTP " + code);

                StringBuilder json = new StringBuilder();
                int total = 0;
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
                    char[] buffer = new char[8192];
                    int count;
                    while ((count = reader.read(buffer)) >= 0) {
                        total += count;
                        if (total > MAX_CATALOG_BYTES) {
                            throw new IllegalStateException("Mod catalog exceeds 2 MiB limit.");
                        }
                        json.append(buffer, 0, count);
                    }
                }

                JSONObject root = new JSONObject(json.toString());
                validate(root);
                success.accept(root);
            } catch (Exception e) {
                failure.accept("Mod server check failed: " +
                        (e.getMessage() == null ? e.toString() : e.getMessage()));
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    static void fetch(String catalogUrl, Consumer<String> success, Consumer<String> failure) {
        fetchCatalog(catalogUrl, root -> {
            JSONArray mods = root.optJSONArray("mods");
            int count = mods == null ? 0 : mods.length();
            StringBuilder display = new StringBuilder();
            display.append("Mod server online\nCatalog version: ")
                    .append(root.optInt("schemaVersion", 1))
                    .append("\nAvailable mods: ").append(count);
            for (int i = 0; mods != null && i < Math.min(count, 8); i++) {
                JSONObject mod = mods.optJSONObject(i);
                if (mod == null) continue;
                display.append("\n\n• ")
                        .append(mod.optString("name", mod.optString("id", "Unnamed mod")))
                        .append(" ").append(mod.optString("version", ""));
            }
            success.accept(display.toString());
        }, failure);
    }

    private static void validate(JSONObject root) throws Exception {
        int schema = root.getInt("schemaVersion");
        if (schema != SUPPORTED_SCHEMA) {
            throw new IllegalArgumentException("Unsupported mod catalog schema " + schema + ".");
        }
        JSONArray mods = root.getJSONArray("mods");
        Set<String> ids = new HashSet<>();
        for (int i = 0; i < mods.length(); i++) {
            JSONObject mod = mods.getJSONObject(i);
            String id = ModInstaller.safeId(mod.getString("id"));
            if (!ids.add(id)) throw new IllegalArgumentException("Duplicate mod id: " + id);
            String name = mod.getString("name").trim();
            String version = mod.getString("version").trim();
            String category = ModInstaller.safeId(mod.getString("category"));
            String url = mod.getString("downloadUrl");
            String sha = mod.getString("sha256");
            String installTarget = mod.optString("installTarget", "library");
            if (name.isEmpty() || version.isEmpty()) {
                throw new IllegalArgumentException("Mod " + id + " has an empty name/version.");
            }
            if (!isCategory(category)) {
                throw new IllegalArgumentException("Mod " + id + " uses unsupported category " + category + ".");
            }
            if (!installTarget.equals("library") &&
                    !installTarget.equals("custom-track") &&
                    !installTarget.equals("texture-pack") &&
                    !installTarget.equals("legacy-track") &&
                    !installTarget.equals("legacy-character")) {
                throw new IllegalArgumentException("Mod " + id + " uses unsupported installTarget " + installTarget + ".");
            }
            if (!url.startsWith("https://")) {
                throw new IllegalArgumentException("Mod " + id + " download must use HTTPS.");
            }
            if (!sha.matches("(?i)[0-9a-f]{64}")) {
                throw new IllegalArgumentException("Mod " + id + " has an invalid SHA-256.");
            }
            long size = mod.optLong("size", -1);
            if (size > 512L * 1024L * 1024L) {
                throw new IllegalArgumentException("Mod " + id + " exceeds the 512 MiB archive limit.");
            }

            JSONArray revisions = mod.optJSONArray("gameRevisions");
            if (revisions != null) {
                for (int j = 0; j < revisions.length(); j++) {
                    String revision = revisions.getString(j);
                    if (!revision.equals("v77") && !revision.equals("v80")) {
                        throw new IllegalArgumentException("Mod " + id + " has unsupported ROM revision " + revision + ".");
                    }
                }
            }

            validateIdArray(mod, id, "dependencies");
            validateIdArray(mod, id, "conflicts");
        }
    }

    private static void validateIdArray(JSONObject mod, String id, String field) throws Exception {
        JSONArray values = mod.optJSONArray(field);
        if (values == null) return;
        Set<String> unique = new HashSet<>();
        for (int i = 0; i < values.length(); i++) {
            String value = ModInstaller.safeId(values.getString(i));
            if (id.equals(value)) {
                throw new IllegalArgumentException("Mod " + id + " cannot list itself in " + field + ".");
            }
            if (!unique.add(value)) {
                throw new IllegalArgumentException("Mod " + id + " repeats " + value + " in " + field + ".");
            }
        }
    }

    private static boolean isCategory(String value) {
        return value.equals("translations") || value.equals("textures") ||
                value.equals("characters") || value.equals("tracks") ||
                value.equals("gameplay") || value.equals("ui");
    }
}
