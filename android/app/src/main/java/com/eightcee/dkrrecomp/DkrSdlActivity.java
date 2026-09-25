package com.eightcee.dkrrecomp;

import android.os.Bundle;
import android.util.Log;

import org.libsdl.app.SDLActivity;

import java.io.File;

public final class DkrSdlActivity extends SDLActivity {
    private static final String TAG = "DKR-R-SDL";

    @Override
    protected void onCreate(Bundle state) {
        Log.i(TAG, "Starting DKR-R SDL host");
        super.onCreate(state);
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
}
