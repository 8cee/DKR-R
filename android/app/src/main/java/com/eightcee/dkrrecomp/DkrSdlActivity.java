package com.eightcee.dkrrecomp;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import android.view.SurfaceHolder;

import org.libsdl.app.SDLActivity;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;

public final class DkrSdlActivity extends SDLActivity {
    private static final String TAG = "DKR-R-SDL";
    private static final int NATIVE_PICK_BASE = 3000;
    private static volatile DkrSdlActivity activeInstance;
    private static volatile int pendingNativeKind = -1;

    @Override
    protected void onCreate(Bundle state) {
        Log.i(TAG, "Starting DKR-R SDL host");
        activeInstance = this;
        super.onCreate(state);
        nativeBridgeInit();

        if (mSurface != null) {
            mSurface.getHolder().addCallback(new SurfaceHolder.Callback() {
                @Override public void surfaceCreated(SurfaceHolder holder) {
                    nativeSurfaceState(true);
                }
                @Override public void surfaceChanged(
                        SurfaceHolder holder, int format, int width, int height) {
                    nativeSurfaceState(true);
                }
                @Override public void surfaceDestroyed(SurfaceHolder holder) {
                    nativeSurfaceState(false);
                }
            });
        }
    }

    public static boolean requestNativeFilePicker(int kind) {
        DkrSdlActivity activity = activeInstance;
        if (activity == null || activity.isFinishing() || pendingNativeKind != -1) {
            return false;
        }
        pendingNativeKind = kind;
        activity.runOnUiThread(() -> {
            try {
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                if (kind == 0) {
                    intent.putExtra(Intent.EXTRA_MIME_TYPES,
                            new String[]{"application/octet-stream",
                                    "application/x-n64-rom", "*/*"});
                }
                activity.startActivityForResult(intent, NATIVE_PICK_BASE + kind);
            } catch (Throwable error) {
                Log.e(TAG, "Could not open Android file picker", error);
                pendingNativeKind = -1;
                nativeOnFilePicked(kind, false, "");
            }
        });
        return true;
    }

    private String stageSelection(Uri uri, int kind) throws Exception {
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
        File staged = new File(inbox,
                "picked-" + System.currentTimeMillis() + "-" + kind + extension);
        try (InputStream in = getContentResolver().openInputStream(uri);
             FileOutputStream out = new FileOutputStream(staged)) {
            if (in == null) throw new IllegalStateException("Could not open selected file.");
            byte[] buffer = new byte[64 * 1024];
            long total = 0;
            int read;
            while ((read = in.read(buffer)) > 0) {
                total += read;
                if (total > 1024L * 1024L * 1024L) {
                    throw new IllegalArgumentException("Selected file exceeds 1 GiB.");
                }
                out.write(buffer, 0, read);
            }
            out.getFD().sync();
        }
        return staged.getAbsolutePath();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode >= NATIVE_PICK_BASE && requestCode < NATIVE_PICK_BASE + 32) {
            final int kind = requestCode - NATIVE_PICK_BASE;
            try {
                if (resultCode == RESULT_OK && data != null && data.getData() != null) {
                    nativeOnFilePicked(kind, true, stageSelection(data.getData(), kind));
                } else {
                    nativeOnFilePicked(kind, false, "");
                }
            } catch (Throwable error) {
                Log.e(TAG, "Could not stage selected file", error);
                nativeOnFilePicked(kind, false, "");
            } finally {
                pendingNativeKind = -1;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override protected void onResume() {
        super.onResume();
        nativeHostResumed(true);
    }

    @Override protected void onPause() {
        nativeHostResumed(false);
        super.onPause();
    }

    @Override protected void onDestroy() {
        if (activeInstance == this) activeInstance = null;
        super.onDestroy();
    }

    @Override protected String[] getLibraries() {
        return new String[]{"dkr_android"};
    }

    @Override protected String getMainFunction() {
        return "DKRAndroidHostMain";
    }

    @Override protected String[] getArguments() {
        return new String[]{
                pathOrEmpty(getFilesDir()),
                pathOrEmpty(getExternalFilesDir(null))
        };
    }

    private static String pathOrEmpty(File file) {
        return file == null ? "" : file.getAbsolutePath();
    }

    private static native void nativeBridgeInit();
    private static native void nativeOnFilePicked(int kind, boolean ok, String payload);
    private static native void nativeHostResumed(boolean resumed);
    private static native void nativeSurfaceState(boolean available);
}
