package com.eightcee.dkrrecomp;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;

public final class MainActivity extends Activity {
    private static final int PICK_ROM = 1001;
    private static final int IMPORT_SAVE = 1002;
    private static final int EXPORT_SAVE = 1003;
    private static final int IMPORT_BUNDLE = 1010;
    private static final int EXPORT_BUNDLE = 1011;
    private static final int IMPORT_PAK_BASE = 1100;
    private static final int EXPORT_PAK_BASE = 1200;
    private static final int NATIVE_PICK_BASE = 3000;

    private static volatile MainActivity activeInstance;
    private static volatile int pendingNativeKind = -1;

    private TextView statusView;

    static { System.loadLibrary("dkr_android"); }
    private static native String nativeBootstrap(String filesDir);
    private static native String nativeVersion();
    private static native void nativeSetResumed(boolean resumed);
    private static native void nativeBridgeInit();
    private static native void nativeOnFilePicked(int kind, boolean ok, String stagedPath);
    private static native String nativeSaveStatus();
    private static native String nativeImportSaveFile(int kind, int channel, String sourcePath);
    private static native String nativeExportSaveFile(int kind, int channel, String destinationPath);

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        activeInstance = this;
        nativeBridgeInit();
        String bootstrap = nativeBootstrap(getFilesDir().getAbsolutePath());

        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(48, 32, 48, 32);
        content.setGravity(Gravity.CENTER_HORIZONTAL);

        TextView title = new TextView(this);
        title.setText("DKR-R Android");
        title.setTextSize(30);
        title.setGravity(Gravity.CENTER);
        content.addView(title);

        statusView = new TextView(this);
        statusView.setText("Android bootstrap: " + bootstrap + "\nNative: " + nativeVersion()
                + "\n\nData: " + getFilesDir().getAbsolutePath()
                + "\nSaves: " + new File(getFilesDir(), "saves").getAbsolutePath()
                + "\nMods: " + new File(getFilesDir(), "mods").getAbsolutePath());
        statusView.setTextSize(15);
        statusView.setPadding(0, 24, 0, 24);
        content.addView(statusView);

        addButton(content, "Select legally obtained DKR ROM", this::chooseRom);
        addButton(content, "Import Adventure Save", this::importSave);
        addButton(content, "Export Adventure Save", this::exportSave);
        addButton(content, "Import Full Save Bundle", this::importBundle);
        addButton(content, "Export Full Save Bundle", this::exportBundle);

        for (int channel = 0; channel < SaveTransfer.CONTROLLER_PAK_COUNT; channel++) {
            final int pak = channel;
            addButton(content, "Import Controller Pak " + (pak + 1), () -> importPak(pak));
            addButton(content, "Export Controller Pak " + (pak + 1), () -> exportPak(pak));
        }

        Button mods = new Button(this);
        mods.setText("Check Mod Server");
        mods.setOnClickListener(v -> ModCatalogClient.fetch(BuildConfig.MOD_SERVER_URL,
                text -> runOnUiThread(() -> statusView.setText(text)),
                error -> runOnUiThread(() -> Toast.makeText(this, error, Toast.LENGTH_LONG).show())));
        content.addView(mods);

        TextView note = new TextView(this);
        note.setPadding(0, 24, 0, 0);
        note.setText("The temporary Android host now understands DKR-R Adventure saves, four Controller Paks and DKR-R save bundles. Final checksum-aware Adventure validation will be delegated to the native DKR-R save manager when the full runtime is linked.");
        content.addView(note);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(content);
        setContentView(scroll);
    }

    private void addButton(LinearLayout content, String label, Runnable action) {
        Button button = new Button(this);
        button.setText(label);
        button.setOnClickListener(v -> action.run());
        content.addView(button);
    }

    public static boolean requestNativeFilePicker(int kind) {
        MainActivity activity = activeInstance;
        if (activity == null || activity.isFinishing() || pendingNativeKind != -1) return false;
        pendingNativeKind = kind;
        activity.runOnUiThread(() -> {
            try {
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("application/octet-stream");
                if (kind == 0) {
                    intent.putExtra(Intent.EXTRA_MIME_TYPES,
                            new String[]{"application/octet-stream", "application/x-n64-rom", "*/*"});
                }
                activity.startActivityForResult(intent, NATIVE_PICK_BASE + kind);
            } catch (Exception e) {
                pendingNativeKind = -1;
                nativeOnFilePicked(kind, false, "");
            }
        });
        return true;
    }

    private String stageNativeSelection(Uri uri, int kind) throws Exception {
        File inbox = new File(getCacheDir(), "saf-inbox");
        if (!inbox.exists() && !inbox.mkdirs()) {
            throw new IllegalStateException("Could not create SAF staging directory.");
        }
        String extension;
        switch (kind) {
            case 0: extension = ".rom"; break;
            case 1: extension = ".bin"; break;
            case 2: extension = ".dkrsave"; break;
            case 3: extension = ".mpk"; break;
            case 4: extension = ".zip"; break;
            default: extension = ".dat"; break;
        }
        File staged = new File(inbox, "picked-" + System.currentTimeMillis() + "-" + kind + extension);
        try (InputStream in = getContentResolver().openInputStream(uri);
             FileOutputStream out = new FileOutputStream(staged)) {
            if (in == null) throw new IllegalStateException("Could not open selected file.");
            byte[] buffer = new byte[64 * 1024];
            long total = 0;
            int read;
            while ((read = in.read(buffer)) > 0) {
                total += read;
                if (total > 1024L * 1024L * 1024L) {
                    throw new IllegalArgumentException("Selected file exceeds the 1 GiB staging limit.");
                }
                out.write(buffer, 0, read);
            }
            out.getFD().sync();
        }
        return staged.getAbsolutePath();
    }

    @Override protected void onResume() { super.onResume(); nativeSetResumed(true); }
    @Override protected void onPause() { nativeSetResumed(false); super.onPause(); }

    private void chooseRom() { openFile(PICK_ROM); }
    private void importSave() { openFile(IMPORT_SAVE); }
    private void importBundle() { openFile(IMPORT_BUNDLE); }
    private void importPak(int channel) { openFile(IMPORT_PAK_BASE + channel); }

    private void openFile(int requestCode) {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        if (requestCode == PICK_ROM) {
            intent.putExtra(Intent.EXTRA_MIME_TYPES,
                    new String[]{"application/octet-stream", "application/x-n64-rom", "*/*"});
        }
        startActivityForResult(intent, requestCode);
    }

    private void exportSave() {
        if (!SaveTransfer.adventureFile(getFilesDir()).isFile()) {
            toast("No DKR Adventure save exists yet.");
            return;
        }
        createFile(EXPORT_SAVE, "dkr.us.v77.bin");
    }

    private void exportBundle() { createFile(EXPORT_BUNDLE, "DKR-R-Saves.dkrsave"); }

    private void exportPak(int channel) {
        File pak = SaveTransfer.controllerPakFile(getFilesDir(), channel);
        if (!pak.isFile()) {
            toast("Controller Pak " + (channel + 1) + " does not exist yet.");
            return;
        }
        createFile(EXPORT_PAK_BASE + channel, "controller-pak-" + (channel + 1) + ".mpk");
    }

    private void createFile(int requestCode, String filename) {
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        intent.putExtra(Intent.EXTRA_TITLE, filename);
        startActivityForResult(intent, requestCode);
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();

        if (requestCode >= NATIVE_PICK_BASE && requestCode < NATIVE_PICK_BASE + 32) {
            int kind = requestCode - NATIVE_PICK_BASE;
            try {
                String path = stageNativeSelection(uri, kind);
                nativeOnFilePicked(kind, true, path);
            } catch (Exception e) {
                nativeOnFilePicked(kind, false, "");
            } finally {
                pendingNativeKind = -1;
            }
            return;
        }

        try {
            if (requestCode == IMPORT_SAVE) {
                statusView.setText(nativeImportFromUri(uri, 0, 0, ".bin"));
                return;
            }
            if (requestCode == EXPORT_SAVE) {
                statusView.setText(nativeExportToUri(uri, 0, 0, ".bin"));
                return;
            }
            if (requestCode == IMPORT_BUNDLE) {
                statusView.setText(nativeImportFromUri(uri, 1, 0, ".dkrsave"));
                return;
            }
            if (requestCode == EXPORT_BUNDLE) {
                statusView.setText(nativeExportToUri(uri, 1, 0, ".dkrsave"));
                return;
            }
            if (requestCode >= IMPORT_PAK_BASE && requestCode < IMPORT_PAK_BASE + SaveTransfer.CONTROLLER_PAK_COUNT) {
                int channel = requestCode - IMPORT_PAK_BASE;
                statusView.setText(nativeImportFromUri(uri, 2, channel, ".mpk"));
                return;
            }
            if (requestCode >= EXPORT_PAK_BASE && requestCode < EXPORT_PAK_BASE + SaveTransfer.CONTROLLER_PAK_COUNT) {
                int channel = requestCode - EXPORT_PAK_BASE;
                statusView.setText(nativeExportToUri(uri, 2, channel, ".mpk"));
                return;
            }
            if (requestCode == PICK_ROM) {
                importRom(uri);
            }
        } catch (Exception e) {
            toast("File operation failed: " + e.getMessage());
        }
    }

    private String nativeImportFromUri(Uri uri, int kind, int channel, String extension) throws Exception {
        File dir = new File(getCacheDir(), "save-transfer");
        if (!dir.exists() && !dir.mkdirs()) throw new IllegalStateException("Could not create save staging directory.");
        File staged = new File(dir, "import-" + System.currentTimeMillis() + extension);
        try {
            try (InputStream in = getContentResolver().openInputStream(uri);
                 FileOutputStream out = new FileOutputStream(staged)) {
                if (in == null) throw new IllegalStateException("Could not open selected file.");
                byte[] buffer = new byte[64 * 1024];
                int read;
                long total = 0;
                while ((read = in.read(buffer)) > 0) {
                    total += read;
                    if (total > 2L * 1024L * 1024L) throw new IllegalArgumentException("Save file is unexpectedly large.");
                    out.write(buffer, 0, read);
                }
                out.getFD().sync();
            }
            String result = nativeImportSaveFile(kind, channel, staged.getAbsolutePath());
            if (result.startsWith("ERR:")) throw new IllegalArgumentException(result.substring(4));
            return "Native DKR-R save import completed.\n" + nativeSaveStatus();
        } finally {
            staged.delete();
        }
    }

    private String nativeExportToUri(Uri uri, int kind, int channel, String extension) throws Exception {
        File dir = new File(getCacheDir(), "save-transfer");
        if (!dir.exists() && !dir.mkdirs()) throw new IllegalStateException("Could not create save staging directory.");
        File staged = new File(dir, "export-" + System.currentTimeMillis() + extension);
        try {
            String result = nativeExportSaveFile(kind, channel, staged.getAbsolutePath());
            if (result.startsWith("ERR:")) throw new IllegalArgumentException(result.substring(4));
            try (InputStream in = new java.io.FileInputStream(staged);
                 java.io.OutputStream out = getContentResolver().openOutputStream(uri, "wt")) {
                if (out == null) throw new IllegalStateException("Could not open export destination.");
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = in.read(buffer)) > 0) out.write(buffer, 0, read);
                out.flush();
            }
            return "Native DKR-R save export completed.\n" + nativeSaveStatus();
        } finally {
            staged.delete();
        }
    }

    private void importRom(Uri uri) throws Exception {
        File dst = new File(getFilesDir(), "roms/dkr.rom");
        File parent = dst.getParentFile();
        if (parent != null) parent.mkdirs();
        try (InputStream in = getContentResolver().openInputStream(uri);
             FileOutputStream out = new FileOutputStream(dst)) {
            if (in == null) throw new IllegalStateException("Could not open selected ROM");
            byte[] buffer = new byte[1024 * 1024];
            int read;
            while ((read = in.read(buffer)) > 0) out.write(buffer, 0, read);
        }
        RomInspector.Result inspection = RomInspector.inspect(dst);
        statusView.setText(inspection.describe() + "\n\nStored privately at:\n" + dst.getAbsolutePath());
        if (!inspection.candidate) dst.delete();
    }

    @Override protected void onDestroy() {
        if (activeInstance == this) activeInstance = null;
        super.onDestroy();
    }

    private void toast(String message) { Toast.makeText(this, message, Toast.LENGTH_LONG).show(); }

    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        return ControllerBridge.handleKey(event) || super.dispatchKeyEvent(event);
    }

    @Override public boolean onGenericMotionEvent(MotionEvent event) {
        return ControllerBridge.handleMotion(event) || super.onGenericMotionEvent(event);
    }
}
