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

    private TextView statusView;

    static { System.loadLibrary("dkr_android"); }

    private static native String nativeBootstrap(String filesDir);
    private static native String nativeVersion();
    private static native void nativeSetResumed(boolean resumed);

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
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
        statusView.setText(
                "Android bootstrap: " + bootstrap +
                "\nNative: " + nativeVersion() +
                "\n\nData: " + getFilesDir().getAbsolutePath() +
                "\nSaves: " + new File(getFilesDir(), "saves").getAbsolutePath() +
                "\nMods: " + new File(getFilesDir(), "mods").getAbsolutePath());
        statusView.setTextSize(15);
        statusView.setPadding(0, 24, 0, 24);
        content.addView(statusView);

        Button rom = new Button(this);
        rom.setText("Select legally obtained DKR ROM");
        rom.setOnClickListener(v -> chooseRom());
        content.addView(rom);

        Button importSave = new Button(this);
        importSave.setText("Import Save");
        importSave.setOnClickListener(v -> importSave());
        content.addView(importSave);

        Button exportSave = new Button(this);
        exportSave.setText("Export Save");
        exportSave.setOnClickListener(v -> exportSave());
        content.addView(exportSave);

        Button mods = new Button(this);
        mods.setText("Check Mod Server");
        mods.setOnClickListener(v -> ModCatalogClient.fetch(
                BuildConfig.MOD_SERVER_URL,
                text -> runOnUiThread(() -> statusView.setText(text)),
                error -> runOnUiThread(() ->
                        Toast.makeText(this, error, Toast.LENGTH_LONG).show())));
        content.addView(mods);

        TextView note = new TextView(this);
        note.setPadding(0, 24, 0, 0);
        note.setText(
                "Game data is never bundled. Controller events are captured by the Android bridge. " +
                "Final ROM revision validation remains authoritative in DKR-R's native runtime.");
        content.addView(note);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(content);
        setContentView(scroll);
    }

    @Override protected void onResume() {
        super.onResume();
        nativeSetResumed(true);
    }

    @Override protected void onPause() {
        nativeSetResumed(false);
        super.onPause();
    }

    private void chooseRom() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        intent.putExtra(Intent.EXTRA_MIME_TYPES,
                new String[]{"application/octet-stream", "application/x-n64-rom", "*/*"});
        startActivityForResult(intent, PICK_ROM);
    }

    private void importSave() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        startActivityForResult(intent, IMPORT_SAVE);
    }

    private void exportSave() {
        File save = SaveTransfer.adventureFile(getFilesDir());
        if (!save.isFile()) {
            Toast.makeText(this, "No DKR Adventure save exists yet.", Toast.LENGTH_LONG).show();
            return;
        }
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        intent.putExtra(Intent.EXTRA_TITLE, "dkr.us.v77.bin");
        startActivityForResult(intent, EXPORT_SAVE);
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null || data.getData() == null) return;

        Uri uri = data.getData();

        if (requestCode == IMPORT_SAVE) {
            try {
                String result = SaveTransfer.importAdventure(
                        getContentResolver(), uri, getFilesDir());
                statusView.setText(
                        result + "\n\nActive save:\n" +
                        SaveTransfer.adventureFile(getFilesDir()).getAbsolutePath());
            } catch (Exception e) {
                Toast.makeText(this,
                        "Save import failed: " + e.getMessage(),
                        Toast.LENGTH_LONG).show();
            }
            return;
        }

        if (requestCode == EXPORT_SAVE) {
            try {
                String result = SaveTransfer.exportAdventure(
                        getContentResolver(), uri, getFilesDir());
                statusView.setText(result);
            } catch (Exception e) {
                Toast.makeText(this,
                        "Save export failed: " + e.getMessage(),
                        Toast.LENGTH_LONG).show();
            }
            return;
        }

        if (requestCode != PICK_ROM) return;

        File dst = new File(getFilesDir(), "roms/dkr.rom");
        File parent = dst.getParentFile();
        if (parent != null) parent.mkdirs();

        try (InputStream in = getContentResolver().openInputStream(uri);
             FileOutputStream out = new FileOutputStream(dst)) {
            if (in == null) throw new IllegalStateException("Could not open selected ROM");
            byte[] buffer = new byte[1024 * 1024];
            int read;
            while ((read = in.read(buffer)) > 0) out.write(buffer, 0, read);

            RomInspector.Result inspection = RomInspector.inspect(dst);
            statusView.setText(
                    inspection.describe() +
                    "\n\nStored privately at:\n" + dst.getAbsolutePath());
            if (!inspection.candidate) dst.delete();
        } catch (Exception e) {
            Toast.makeText(this,
                    "ROM import failed: " + e.getMessage(),
                    Toast.LENGTH_LONG).show();
        }
    }

    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        return ControllerBridge.handleKey(event) || super.dispatchKeyEvent(event);
    }

    @Override public boolean onGenericMotionEvent(MotionEvent event) {
        return ControllerBridge.handleMotion(event) || super.onGenericMotionEvent(event);
    }
}
