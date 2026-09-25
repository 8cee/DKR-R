package com.eightcee.dkrrecomp;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

final class ModCatalogClient {
    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();

    private ModCatalogClient() {}

    static void fetch(String catalogUrl, Consumer<String> success, Consumer<String> failure) {
        EXECUTOR.execute(() -> {
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) new URL(catalogUrl).openConnection();
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(8000);
                connection.setRequestProperty("Accept", "application/json");
                if (connection.getResponseCode() != 200) {
                    throw new IllegalStateException("Mod server HTTP " + connection.getResponseCode());
                }

                StringBuilder json = new StringBuilder();
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) json.append(line);
                }

                JSONObject root = new JSONObject(json.toString());
                JSONArray mods = root.optJSONArray("mods");
                int count = mods == null ? 0 : mods.length();

                StringBuilder display = new StringBuilder();
                display.append("Mod server online\nCatalog version: ")
                       .append(root.optInt("schemaVersion", 1))
                       .append("\nAvailable mods: ").append(count);

                for (int i = 0; mods != null && i < Math.min(count, 8); i++) {
                    JSONObject mod = mods.getJSONObject(i);
                    display.append("\n\n• ").append(mod.optString("name", mod.optString("id", "Unnamed mod")))
                           .append(" ").append(mod.optString("version", ""));
                }
                success.accept(display.toString());
            } catch (Exception e) {
                failure.accept("Mod server check failed: " + e.getMessage());
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }
}
