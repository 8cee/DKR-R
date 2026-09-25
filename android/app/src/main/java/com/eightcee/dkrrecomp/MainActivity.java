package com.eightcee.dkrrecomp;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
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
    private TextView statusView;

    static {
        System.loadLibrary("dkr_android");
    }

    private static native String nativeBootstrap(String filesDir);
    private static native String nativeVersion();

    @Override
    protected void onCreate(Bundle state) {
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
        statusView.setText("Android bootstrap: " + bootstrap + "\nNative: " + nativeVersion()
                + "\n\nGame data: " + getFilesDir().getAbsolutePath()
                + "\nMods: " + new File(getFilesDir(), "mods").getAbsolutePath());
        statusView.setTextSize(15);
        statusView.setPadding(0, 24, 0, 24);
        content.addView(statusView);

        Button romButton = new Button(this);
        romButton.setText("Select legally obtained DKR ROM");
        romButton.setOnClickListener(v -> chooseRom());
        content.addView(romButton);

        Button modsButton = new Button(this);
        modsButton.setText("Check Mod Server");
        modsButton.setOnClickListener(v -> ModCatalogClient.fetch(BuildConfig.MOD_SERVER_URL,
                text -> runOnUiThread(() -> statusView.setText(text)),
                error -> runOnUiThread(() -> Toast.makeText(this, error, Toast.LENGTH_LONG).show())));
        content.addView(modsButton);

        TextView note = new TextView(this);
        note.setPadding(0, 24, 0, 0);
        note.setText("This branch does not ship Nintendo/Rare game data. The native DKR runtime will be linked into this shell as Android portability work progresses.");
        content.addView(note);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(content);
        setContentView(scroll);
    }

    private void chooseRom() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/octet-stream", "application/x-n64-rom", "*/*"});
        startActivityForResult(intent, PICK_ROM);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_ROM || resultCode != RESULT_OK || data == null || data.getData() == null) return;

        Uri uri = data.getData();
        File dst = new File(getFilesDir(), "roms/dkr.z64");
        File parent = dst.getParentFile();
        if (parent != null) parent.mkdirs();

        try (InputStream in = getContentResolver().openInputStream(uri);
             FileOutputStream out = new FileOutputStream(dst)) {
            if (in == null) throw new IllegalStateException("Could not open selected ROM");
            byte[] buffer = new byte[1024 * 1024];
            int read;
            while ((read = in.read(buffer)) > 0) out.write(buffer, 0, read);
            statusView.setText("ROM imported to app-private storage:\n" + dst.getAbsolutePath()
                    + "\n\nNext milestone: validate revision/hash and launch the recompiled runtime.");
        } catch (Exception e) {
            Toast.makeText(this, "ROM import failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }
}
