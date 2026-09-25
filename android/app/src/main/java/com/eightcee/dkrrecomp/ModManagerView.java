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
    private JSONObject currentCatalog;

    ModManagerView(Activity activity) {
        this.activity = activity;
        this.modsRoot = new File(activity.getFilesDir(), "catalog-mods");

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

        refresh();
    }

    View view() {
        return root;
    }

    private void refresh() {
        showLoading();
        ModCatalogClient.fetchCatalog(
                BuildConfig.MOD_SERVER_URL,
                catalog -> activity.runOnUiThread(() -> {
                    currentCatalog = catalog;
                    renderCatalog(catalog);
                }),
                error -> activity.runOnUiThread(() -> {
                    currentCatalog = null;
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
        String revision = ModCompatibility.currentGameRevision(activity.getFilesDir());
        addInfo("Server online • " + count + " mod" + (count == 1 ? "" : "s") +
                "\nApp " + BuildConfig.VERSION_NAME +
                " • ROM " + (revision == null ? "not selected / unsupported" : revision));

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
        String installTarget = mod.optString("installTarget", "library");

        JSONObject installed = ModInstaller.installedMetadata(modsRoot, mod);
        String installedVersion = installed == null ? null : installed.optString("version", "");
        boolean sameVersion = installedVersion != null && installedVersion.equals(version);
        ModCompatibility.Verdict installVerdict =
                ModCompatibility.canInstall(activity.getFilesDir(), modsRoot, mod);

        TextView title = new TextView(activity);
        title.setText(name + (version.isEmpty() ? "" : "  " + version));
        title.setTextSize(18);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        title.setPadding(0, 22, 0, 2);
        root.addView(title);

        StringBuilder details = new StringBuilder(category);
        if (!installTarget.equals("library")) details.append(" • activates as ").append(installTarget);
        if (!author.isEmpty()) details.append(" • by ").append(author);
        if (installedVersion != null) {
            details.append("\nInstalled: ").append(installedVersion.isEmpty() ? "unknown" : installedVersion);
        }
        appendCompatibility(details, mod);
        if (!installVerdict.allowed) details.append("\nBlocked: ").append(installVerdict.reason);
        if (!description.isEmpty()) details.append("\n").append(description);

        TextView detailView = new TextView(activity);
        detailView.setText(details.toString());
        detailView.setPadding(0, 0, 0, 4);
        root.addView(detailView);

        LinearLayout actions = new LinearLayout(activity);
        actions.setOrientation(LinearLayout.HORIZONTAL);

        Button install = new Button(activity);
        install.setText(installed == null ? "Install" : (sameVersion ? "Reinstall" : "Update"));
        install.setEnabled(installVerdict.allowed);
        install.setOnClickListener(v -> installMod(mod, install));
        actions.addView(install);

        if (installed != null) {
            ModCompatibility.Verdict removeVerdict = ModCompatibility.canRemove(modsRoot, mod);
            Button remove = new Button(activity);
            remove.setText("Remove");
            remove.setEnabled(removeVerdict.allowed);
            if (!removeVerdict.reason.isEmpty()) remove.setContentDescription(removeVerdict.reason);
            JSONObject installedMetadata = installed;
            remove.setOnClickListener(v -> removeMod(mod, installedMetadata, remove));
            actions.addView(remove);
            if (!removeVerdict.allowed) {
                TextView removalNote = new TextView(activity);
                removalNote.setText("Cannot remove: " + removeVerdict.reason);
                removalNote.setPadding(0, 2, 0, 2);
                root.addView(removalNote);
            }
        }
        root.addView(actions);
    }

    private void appendCompatibility(StringBuilder details, JSONObject mod) {
        JSONArray revisions = mod.optJSONArray("gameRevisions");
        if (revisions != null && revisions.length() > 0) {
            details.append("\nROM: ");
            for (int i = 0; i < revisions.length(); i++) {
                if (i > 0) details.append(", ");
                details.append(revisions.optString(i));
            }
        }
        String minApp = mod.optString("minAppVersion", "").trim();
        if (!minApp.isEmpty()) details.append("\nRequires app ").append(minApp).append("+");

        JSONArray dependencies = mod.optJSONArray("dependencies");
        if (dependencies != null && dependencies.length() > 0) {
            details.append("\nRequires: ");
            appendArray(details, dependencies);
        }

        JSONArray conflicts = mod.optJSONArray("conflicts");
        if (conflicts != null && conflicts.length() > 0) {
            details.append("\nConflicts: ");
            appendArray(details, conflicts);
        }
    }

    private static void appendArray(StringBuilder out, JSONArray values) {
        for (int i = 0; i < values.length(); i++) {
            if (i > 0) out.append(", ");
            out.append(values.optString(i));
        }
    }

    private void installMod(JSONObject mod, Button button) {
        ModCompatibility.Verdict verdict =
                ModCompatibility.canInstall(activity.getFilesDir(), modsRoot, mod);
        if (!verdict.allowed) {
            toast(verdict.reason);
            refreshLocal();
            return;
        }

        final String name = mod.optString("name", mod.optString("id", "mod"));
        final JSONObject previousInstall = ModInstaller.installedMetadata(modsRoot, mod);
        button.setEnabled(false);
        button.setText("Installing…");
        ModInstaller.install(modsRoot, mod, new ModInstaller.Callback() {
            @Override public void onSuccess(File installedDirectory) {
                String target = mod.optString("installTarget", "library");
                File archive = ModInstaller.packageArchive(installedDirectory);
                CatalogModNative.Result activation =
                        CatalogModNative.activate(activity.getFilesDir(), archive, target);
                if (activation.ok) {
                    ModInstaller.recordActivation(
                            installedDirectory, target, activation.nativeId);
                    if (previousInstall != null) {
                        String previousTarget = previousInstall.optString("activatedTarget", "library");
                        String previousId = previousInstall.optString("activatedNativeId", "");
                        if (!previousId.isEmpty() &&
                                previousTarget.equals(target) &&
                                !previousId.equals(activation.nativeId)) {
                            CatalogModNative.deactivate(
                                    activity.getFilesDir(), previousTarget, previousId);
                        }
                    }
                }
                activity.runOnUiThread(() -> {
                    if (activation.ok) {
                        toast(name + ": " + activation.message);
                    } else {
                        toast(name + " downloaded, but activation failed: " + activation.message);
                    }
                    refreshLocal();
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

    private void removeMod(JSONObject mod, JSONObject installedMetadata, Button button) {
        ModCompatibility.Verdict verdict = ModCompatibility.canRemove(modsRoot, mod);
        if (!verdict.allowed) {
            toast(verdict.reason);
            refreshLocal();
            return;
        }

        String name = mod.optString("name", mod.optString("id", "mod"));
        String target = installedMetadata.optString(
                "activatedTarget", mod.optString("installTarget", "library"));
        String nativeId = installedMetadata.optString("activatedNativeId", "");

        button.setEnabled(false);
        button.setText("Removing…");

        new Thread(() -> {
            CatalogModNative.Result deactivation;
            if (!target.equals("library") && nativeId.isEmpty()) {
                deactivation = new CatalogModNative.Result(
                        true, "", "Unactivated catalog package removed.");
            } else {
                deactivation = CatalogModNative.deactivate(
                        activity.getFilesDir(), target, nativeId);
            }
            boolean catalogRemoved = false;
            if (deactivation.ok) {
                catalogRemoved = ModInstaller.remove(modsRoot, mod);
            }
            final boolean removed = catalogRemoved;
            activity.runOnUiThread(() -> {
                if (!deactivation.ok) {
                    button.setEnabled(true);
                    button.setText("Retry remove");
                    toast("Could not deactivate " + name + ": " + deactivation.message);
                    return;
                }
                if (!removed) {
                    button.setEnabled(true);
                    button.setText("Retry remove");
                    toast(name + " was deactivated, but its catalog copy could not be removed.");
                    return;
                }
                toast(name + ": " + deactivation.message);
                refreshLocal();
            });
        }, "DKR-CatalogModRemove").start();
    }

    private void refreshLocal() {
        if (currentCatalog != null) renderCatalog(currentCatalog);
        else refresh();
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
