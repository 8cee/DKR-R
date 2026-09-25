package com.eightcee.dkrrecomp;

import android.app.Activity;
import android.graphics.Typeface;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;

final class ModManagerView {
    private final Activity activity;
    private final LinearLayout root;
    private final File modsRoot;

    ModManagerView(Activity activity) {
        this.activity = activity;
        this.modsRoot = new File(activity.getFilesDir(), "mods");

        root = new LinearLayout(activity);
        root.setOrientation(LinearLayout.VERTICAL);

        TextView heading = new TextView(activity);
        heading.setText("Mods / Hacks");
        heading.setTextSize(22);
        heading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        heading.setPadding(0, 28, 0, 8);
        root.addView(heading);

        TextView summary = new TextView(activity);
        summary.setText("Browse, install, update and remove mods from the configured DKR-R catalog.");
        summary.setPadding(0, 0, 0, 8);
        root.addView(summary);

        Button refresh = new Button(activity);
        refresh.setText("Refresh Mod Server");
        refresh.setOnClickListener(v -> refresh());
        root.addView(refresh);
    }

    View view() {
        return root;
    }

    private void refresh() {
        showLoading();
        ModCatalogClient.fetchCatalog(
                BuildConfig.MOD_SERVER_URL,
                catalog -> activity.runOnUiThread(() -> renderCatalog(catalog)),
                error -> activity.runOnUiThread(() -> {
                    clearDynamicRows();
                    addInfo(error);
                    toast(error);
                }));
    }

    private void showLoading() {
        clearDynamicRows();
        addInfo("Loading mod catalog…");
    }

    private void renderCatalog(JSONObject catalog) {
        clearDynamicRows();
        JSONArray mods = catalog.optJSONArray("mods");
        int count = mods == null ? 0 : mods.length();
        addInfo("Server online • " + count + " mod" + (count == 1 ? "" : "s"));

        if (count == 0) {
            addInfo("No mods are published in the catalog yet.");
            return;
        }

        for (int i = 0; i < count; i++) {
            JSONObject mod = mods.optJSONObject(i);
            if (mod != null) addModRow(mod);
        }
    }

    private void addModRow(JSONObject mod) {
        String name = mod.optString("name", mod.optString("id", "Unnamed mod"));
        String version = mod.optString("version", "");
        String category = mod.optString("category", "gameplay");
        String author = mod.optString("author", "");
        String description = mod.optString("description", "");

        JSONObject installed = ModInstaller.installedMetadata(modsRoot, mod);
        String installedVersion = installed == null ? null : installed.optString("version", "");
        boolean sameVersion = installedVersion != null && installedVersion.equals(version);

        TextView title = new TextView(activity);
        title.setText(name + (version.isEmpty() ? "" : "  " + version));
        title.setTextSize(18);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        title.setPadding(0, 22, 0, 2);
        root.addView(title);

        StringBuilder details = new StringBuilder(category);
        if (!author.isEmpty()) details.append(" • by ").append(author);
        if (installedVersion != null) {
            details.append("\nInstalled: ").append(installedVersion.isEmpty() ? "unknown" : installedVersion);
        }
        if (!description.isEmpty()) details.append("\n").append(description);
        TextView detailView = new TextView(activity);
        detailView.setText(details.toString());
        detailView.setPadding(0, 0, 0, 4);
        root.addView(detailView);

        LinearLayout actions = new LinearLayout(activity);
        actions.setOrientation(LinearLayout.HORIZONTAL);

        Button install = new Button(activity);
        install.setText(installed == null ? "Install" : (sameVersion ? "Reinstall" : "Update"));
        install.setOnClickListener(v -> installMod(mod, install));
        actions.addView(install);

        if (installed != null) {
            Button remove = new Button(activity);
            remove.setText("Remove");
            remove.setOnClickListener(v -> {
                if (ModInstaller.remove(modsRoot, mod)) {
                    toast(name + " removed.");
                    refresh();
                } else {
                    toast("Could not remove " + name + ".");
                }
            });
            actions.addView(remove);
        }
        root.addView(actions);
    }

    private void installMod(JSONObject mod, Button button) {
        final String name = mod.optString("name", mod.optString("id", "mod"));
        button.setEnabled(false);
        button.setText("Installing…");
        ModInstaller.install(modsRoot, mod, new ModInstaller.Callback() {
            @Override public void onSuccess(File installedDirectory) {
                activity.runOnUiThread(() -> {
                    toast(name + " installed.");
                    refresh();
                });
            }

            @Override public void onFailure(String error) {
                activity.runOnUiThread(() -> {
                    button.setEnabled(true);
                    button.setText("Retry");
                    toast("Install failed: " + error);
                });
            }
        });
    }

    private void clearDynamicRows() {
        while (root.getChildCount() > 3) root.removeViewAt(root.getChildCount() - 1);
    }

    private void addInfo(String text) {
        TextView info = new TextView(activity);
        info.setText(text);
        info.setPadding(0, 12, 0, 4);
        root.addView(info);
    }

    private void toast(String message) {
        Toast.makeText(activity, message, Toast.LENGTH_LONG).show();
    }
}
