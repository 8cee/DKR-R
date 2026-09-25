package com.eightcee.dkrrecomp;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

final class ModCompatibility {
    static final class Verdict {
        final boolean allowed;
        final String reason;

        Verdict(boolean allowed, String reason) {
            this.allowed = allowed;
            this.reason = reason;
        }

        static Verdict allow() { return new Verdict(true, ""); }
        static Verdict block(String reason) { return new Verdict(false, reason); }
    }

    private ModCompatibility() {}

    static String currentGameRevision(File filesDir) {
        File rom = new File(filesDir, "roms/dkr.rom");
        if (!rom.isFile()) return null;
        return revisionTag(RomInspector.inspect(rom));
    }

    static String revisionTag(RomInspector.Result result) {
        if (result == null || !result.candidate || result.country != 0x45) return null; // NTSC-U
        if (result.revision == 0) return "v77";
        if (result.revision == 1) return "v80";
        return null;
    }

    static Verdict canInstall(File filesDir, File modsRoot, JSONObject mod) {
        String minApp = mod.optString("minAppVersion", "").trim();
        if (!minApp.isEmpty() && compareVersions(BuildConfig.VERSION_NAME, minApp) < 0) {
            return Verdict.block("Requires DKR-R Android " + minApp + " or newer.");
        }

        JSONArray revisions = mod.optJSONArray("gameRevisions");
        if (revisions != null && revisions.length() > 0) {
            String current = currentGameRevision(filesDir);
            if (current == null) {
                return Verdict.block("Select a supported US DKR ROM before installing this mod.");
            }
            boolean supported = false;
            for (int i = 0; i < revisions.length(); i++) {
                if (current.equals(revisions.optString(i))) {
                    supported = true;
                    break;
                }
            }
            if (!supported) {
                return Verdict.block("This mod does not support the selected ROM revision (" + current + ").");
            }
        }

        JSONArray dependencies = mod.optJSONArray("dependencies");
        if (dependencies != null) {
            List<String> missing = new ArrayList<>();
            for (int i = 0; i < dependencies.length(); i++) {
                String id = dependencies.optString(i, "");
                if (!id.isEmpty() && findInstalledById(modsRoot, id) == null) missing.add(id);
            }
            if (!missing.isEmpty()) {
                return Verdict.block("Missing required mod" + (missing.size() == 1 ? ": " : "s: ") +
                        String.join(", ", missing));
            }
        }

        JSONArray conflicts = mod.optJSONArray("conflicts");
        if (conflicts != null) {
            List<String> active = new ArrayList<>();
            for (int i = 0; i < conflicts.length(); i++) {
                String id = conflicts.optString(i, "");
                if (!id.isEmpty() && findInstalledById(modsRoot, id) != null) active.add(id);
            }
            if (!active.isEmpty()) {
                return Verdict.block("Conflicts with installed mod" + (active.size() == 1 ? ": " : "s: ") +
                        String.join(", ", active));
            }
        }

        return Verdict.allow();
    }

    static Verdict canRemove(File modsRoot, JSONObject mod) {
        String id = mod.optString("id", "");
        if (id.isEmpty()) return Verdict.allow();

        List<String> dependents = new ArrayList<>();
        for (JSONObject installed : allInstalledMetadata(modsRoot)) {
            if (id.equals(installed.optString("id"))) continue;
            JSONArray dependencies = installed.optJSONArray("dependencies");
            if (dependencies == null) continue;
            for (int i = 0; i < dependencies.length(); i++) {
                if (id.equals(dependencies.optString(i))) {
                    dependents.add(installed.optString("name", installed.optString("id", "unknown")));
                    break;
                }
            }
        }
        if (!dependents.isEmpty()) {
            return Verdict.block("Required by installed mod" + (dependents.size() == 1 ? ": " : "s: ") +
                    String.join(", ", dependents));
        }
        return Verdict.allow();
    }

    static JSONObject findInstalledById(File modsRoot, String id) {
        for (JSONObject metadata : allInstalledMetadata(modsRoot)) {
            if (id.equals(metadata.optString("id"))) return metadata;
        }
        return null;
    }

    private static List<JSONObject> allInstalledMetadata(File modsRoot) {
        List<JSONObject> result = new ArrayList<>();
        if (modsRoot == null || !modsRoot.isDirectory()) return result;
        File[] categories = modsRoot.listFiles(File::isDirectory);
        if (categories == null) return result;
        for (File category : categories) {
            if (category.getName().startsWith(".")) continue;
            File[] mods = category.listFiles(File::isDirectory);
            if (mods == null) continue;
            for (File modDir : mods) {
                if (modDir.getName().startsWith(".")) continue;
                JSONObject metadata = ModInstaller.readMetadata(new File(modDir, "mod.json"));
                if (metadata != null) result.add(metadata);
            }
        }
        return result;
    }

    static int compareVersions(String left, String right) {
        String[] a = normalizeVersion(left).split("\\.");
        String[] b = normalizeVersion(right).split("\\.");
        int count = Math.max(a.length, b.length);
        for (int i = 0; i < count; i++) {
            int ai = i < a.length ? parsePart(a[i]) : 0;
            int bi = i < b.length ? parsePart(b[i]) : 0;
            if (ai != bi) return Integer.compare(ai, bi);
        }
        return 0;
    }

    private static String normalizeVersion(String value) {
        if (value == null) return "0";
        String normalized = value.trim().toLowerCase(Locale.ROOT);
        if (normalized.startsWith("v")) normalized = normalized.substring(1);
        int suffix = normalized.indexOf('-');
        if (suffix >= 0) normalized = normalized.substring(0, suffix);
        return normalized.isEmpty() ? "0" : normalized;
    }

    private static int parsePart(String value) {
        int result = 0;
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c < '0' || c > '9') break;
            result = result * 10 + (c - '0');
        }
        return result;
    }
}
