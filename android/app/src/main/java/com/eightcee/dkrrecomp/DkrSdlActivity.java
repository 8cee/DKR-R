package com.eightcee.dkrrecomp;

import android.os.Bundle;
import android.util.Log;
import android.view.SurfaceHolder;

import org.libsdl.app.SDLActivity;

import java.io.File;

public final class DkrSdlActivity extends SDLActivity {
    private static final String TAG = "DKR-R-SDL";

    @Override
    protected void onCreate(Bundle state) {
        Log.i(TAG, "Starting DKR-R SDL host");
        super.onCreate(state);

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

    @Override
    protected void onResume() {
        super.onResume();
        nativeHostResumed(true);
    }

    @Override
    protected void onPause() {
        nativeHostResumed(false);
        super.onPause();
    }

    @Override
    protected String[] getLibraries() {
        return new String[]{"dkr_android"};
    }

    @Override
    protected String getMainFunction() {
        return "DKRAndroidHostMain";
    }

    @Override
    protected String[] getArguments() {
        return new String[]{
                pathOrEmpty(getFilesDir()),
                pathOrEmpty(getExternalFilesDir(null))
        };
    }

    private static String pathOrEmpty(File file) {
        return file == null ? "" : file.getAbsolutePath();
    }

    private static native void nativeHostResumed(boolean resumed);
    private static native void nativeSurfaceState(boolean available);
}
