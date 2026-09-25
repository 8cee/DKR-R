package com.eightcee.dkrrecomp;

import android.content.Intent;
import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.net.Uri;
import android.os.Bundle;
import android.os.SystemClock;
import android.database.Cursor;
import android.provider.OpenableColumns;
import android.util.Log;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.SurfaceHolder;
import android.widget.Button;
import android.widget.RelativeLayout;

import org.libsdl.app.SDLActivity;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.FileInputStream;
import java.io.OutputStream;

public final class DkrSdlActivity extends SDLActivity {
    private static final String TAG = "DKR-R-SDL";
    private static final int NATIVE_PICK_BASE = 3000;
    private static volatile DkrSdlActivity activeInstance;
    private static volatile int pendingNativeKind = -1;
    private static volatile String pendingExportSource = null;
    private static volatile boolean restartRequested = false;
    private VirtualPadView virtualPad;

    @Override
    protected void onCreate(Bundle state) {
        Log.i(TAG, "Starting DKR-R SDL host");
        activeInstance = this;
        try {
            RuntimeAssets.ensureInstalled(this);
        } catch (Exception error) {
            throw new IllegalStateException("Could not install DKR-R runtime assets.", error);
        }
        super.onCreate(state);
        ControllerBridge.register(this);
        nativeBridgeInit();
        nativeRestartInit();

        virtualPad = new VirtualPadView(this);
        RelativeLayout.LayoutParams padLayout = new RelativeLayout.LayoutParams(
                RelativeLayout.LayoutParams.MATCH_PARENT,
                RelativeLayout.LayoutParams.MATCH_PARENT);
        mLayout.addView(virtualPad, padLayout);

        Button touchToggle = new Button(this);
        touchToggle.setText(virtualPad.isPadVisible() ? "HIDE" : "TOUCH");
        touchToggle.setAlpha(0.72f);
        touchToggle.setOnClickListener(v -> {
            virtualPad.setPadVisible(!virtualPad.isPadVisible());
            touchToggle.setText(virtualPad.isPadVisible() ? "HIDE" : "TOUCH");
        });
        RelativeLayout.LayoutParams toggleLayout = new RelativeLayout.LayoutParams(
                RelativeLayout.LayoutParams.WRAP_CONTENT,
                RelativeLayout.LayoutParams.WRAP_CONTENT);
        toggleLayout.addRule(RelativeLayout.ALIGN_PARENT_END);
        toggleLayout.addRule(RelativeLayout.ALIGN_PARENT_BOTTOM);
        toggleLayout.setMargins(12, 12, 20, 20);
        mLayout.addView(touchToggle, toggleLayout);

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
            SurfaceHolder holder = mSurface.getHolder();
            nativeSurfaceState(holder.getSurface() != null
                    && holder.getSurface().isValid());
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

    public static boolean requestNativeExport(
            int kind, String sourcePath, String suggestedName) {
        DkrSdlActivity activity = activeInstance;
        if (activity == null || activity.isFinishing() ||
                pendingNativeKind != -1 || sourcePath == null ||
                sourcePath.isEmpty()) {
            return false;
        }
        File source = new File(sourcePath);
        if (!source.isFile()) return false;

        pendingNativeKind = kind;
        pendingExportSource = sourcePath;
        activity.runOnUiThread(() -> {
            try {
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType(kind == 23 ? "text/plain" : "application/octet-stream");
                intent.putExtra(Intent.EXTRA_TITLE,
                        suggestedName == null || suggestedName.isEmpty()
                                ? "dkr-r-export.bin" : suggestedName);
                activity.startActivityForResult(intent, NATIVE_PICK_BASE + kind);
            } catch (Throwable error) {
                Log.e(TAG, "Could not open Android export picker", error);
                pendingNativeKind = -1;
                pendingExportSource = null;
                nativeOnFilePicked(kind, false, "");
            }
        });
        return true;
    }

    private void finishExport(Uri uri, int kind) throws Exception {
        String sourcePath = pendingExportSource;
        if (sourcePath == null || sourcePath.isEmpty()) {
            throw new IllegalStateException("No native export source is pending.");
        }
        File source = new File(sourcePath);
        if (!source.isFile()) {
            throw new IllegalStateException("Native export staging file is missing.");
        }
        try (InputStream in = new FileInputStream(source);
             OutputStream out = getContentResolver().openOutputStream(uri, "wt")) {
            if (out == null) {
                throw new IllegalStateException("Could not open export destination.");
            }
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = in.read(buffer)) > 0) {
                out.write(buffer, 0, read);
            }
            out.flush();
        }
    }

    private String displayName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(
                uri, new String[]{OpenableColumns.DISPLAY_NAME},
                null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                String name = cursor.getString(0);
                if (name != null && !name.isEmpty()) return name;
            }
        } catch (Throwable ignored) {
        }
        return "selection.dat";
    }

    private String stageSelection(Uri uri, int kind) throws Exception {
        File inbox = new File(getCacheDir(), "saf-inbox");
        if (!inbox.exists() && !inbox.mkdirs()) {
            throw new IllegalStateException("Could not create SAF staging directory.");
        }
        String name = displayName(uri).replaceAll("[^A-Za-z0-9._-]", "_");
        if (name.length() > 120) name = name.substring(name.length() - 120);
        File staged = new File(inbox,
                "picked-" + System.currentTimeMillis() + "-" + kind + "-" + name);
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
                    if (kind >= 20) {
                        finishExport(data.getData(), kind);
                        nativeOnFilePicked(kind, true, data.getData().toString());
                    } else {
                        nativeOnFilePicked(kind, true, stageSelection(data.getData(), kind));
                    }
                } else {
                    nativeOnFilePicked(kind, false, "");
                }
            } catch (Throwable error) {
                Log.e(TAG, "Could not stage selected file", error);
                nativeOnFilePicked(kind, false, "");
            } finally {
                pendingNativeKind = -1;
                pendingExportSource = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    public static void handleNativeAppRestart() {
        DkrSdlActivity activity = activeInstance;
        if (activity == null || activity.isFinishing()) return;

        restartRequested = true;
        try {
            Intent launch = activity.getPackageManager()
                    .getLaunchIntentForPackage(activity.getPackageName());
            AlarmManager alarm =
                    (AlarmManager) activity.getSystemService(Context.ALARM_SERVICE);
            if (launch != null && alarm != null) {
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                        | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
                PendingIntent pending = PendingIntent.getActivity(
                        activity, 0, launch,
                        PendingIntent.FLAG_UPDATE_CURRENT
                                | PendingIntent.FLAG_IMMUTABLE);
                alarm.set(
                        AlarmManager.ELAPSED_REALTIME_WAKEUP,
                        SystemClock.elapsedRealtime() + 1200L,
                        pending);
            }
        } catch (Throwable error) {
            Log.w(TAG, "Could not schedule automatic DKR-R relaunch", error);
        }

        activity.runOnUiThread(() -> {
            if (!activity.isFinishing()) activity.finish();
        });
    }

    @Override protected void onResume() {
        super.onResume();
        nativeHostResumed(true);
    }

    @Override protected void onPause() {
        if (virtualPad != null) {
            virtualPad.releaseInput();
        }
        nativeHostResumed(false);
        super.onPause();
    }

    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        // Mirror controller state into DKR-R's Android bridge, but do not
        // consume the event: SDLActivity must still receive it for launcher
        // navigation, hotplug/controller bookkeeping and SDL mappings.
        ControllerBridge.handleKey(event);
        return super.dispatchKeyEvent(event);
    }

    @Override public boolean onGenericMotionEvent(MotionEvent event) {
        ControllerBridge.handleMotion(event);
        return super.onGenericMotionEvent(event);
    }

    @Override protected void onDestroy() {
        ControllerBridge.unregister();
        if (activeInstance == this) activeInstance = null;
        boolean killForRestart = restartRequested;
        restartRequested = false;
        super.onDestroy();
        if (killForRestart) {
            android.os.Process.killProcess(android.os.Process.myPid());
        }
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
    private static native void nativeRestartInit();
    private static native void nativeOnFilePicked(int kind, boolean ok, String payload);
    private static native void nativeHostResumed(boolean resumed);
    private static native void nativeSurfaceState(boolean available);
}
