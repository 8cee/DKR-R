package com.eightcee.dkrrecomp;

import android.content.ContentResolver;
import android.net.Uri;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

final class SaveTransfer {
    static final int ADVENTURE_SIZE = 0x200;

    private SaveTransfer() {}

    static File adventureFile(File filesDir) {
        return new File(new File(filesDir, "saves"), "dkr.us.v77.bin");
    }

    static String importAdventure(ContentResolver resolver, Uri source, File filesDir) throws Exception {
        File saves = new File(filesDir, "saves");
        if (!saves.exists() && !saves.mkdirs()) {
            throw new IllegalStateException("Could not create save directory.");
        }

        File temporary = new File(saves, "dkr.us.v77.bin.importing");
        long count = 0;
        try (InputStream in = resolver.openInputStream(source);
             FileOutputStream out = new FileOutputStream(temporary)) {
            if (in == null) throw new IllegalStateException("Could not open selected save.");
            byte[] buffer = new byte[4096];
            int read;
            while ((read = in.read(buffer)) > 0) {
                count += read;
                if (count > ADVENTURE_SIZE) {
                    throw new IllegalArgumentException("Selected file is larger than a 512-byte DKR Adventure save.");
                }
                out.write(buffer, 0, read);
            }
            out.getFD().sync();
        } catch (Exception e) {
            temporary.delete();
            throw e;
        }

        if (count != ADVENTURE_SIZE) {
            temporary.delete();
            throw new IllegalArgumentException("Selected file is not exactly 512 bytes.");
        }

        File destination = adventureFile(filesDir);
        File backup = null;
        if (destination.exists()) {
            File backupDir = new File(filesDir, "save-backups");
            if (!backupDir.exists() && !backupDir.mkdirs()) {
                temporary.delete();
                throw new IllegalStateException("Could not create save backup directory.");
            }
            String stamp = new SimpleDateFormat("yyyyMMdd-HHmmss-SSS", Locale.US).format(new Date());
            backup = new File(backupDir, "adventure-before-android-import-" + stamp + ".bin");
            Files.copy(destination.toPath(), backup.toPath(), StandardCopyOption.REPLACE_EXISTING);
        }

        try {
            Files.move(temporary.toPath(), destination.toPath(),
                    StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (Exception atomicFailure) {
            try {
                Files.move(temporary.toPath(), destination.toPath(), StandardCopyOption.REPLACE_EXISTING);
            } catch (Exception moveFailure) {
                if (backup != null && backup.exists()) {
                    Files.copy(backup.toPath(), destination.toPath(), StandardCopyOption.REPLACE_EXISTING);
                }
                temporary.delete();
                throw moveFailure;
            }
        }

        return backup == null
                ? "Save imported successfully."
                : "Save imported successfully. Previous save backed up to " + backup.getName();
    }

    static String exportAdventure(ContentResolver resolver, Uri destinationUri, File filesDir) throws Exception {
        File source = adventureFile(filesDir);
        if (!source.isFile()) {
            throw new IllegalStateException("No Adventure save exists yet.");
        }
        if (source.length() != ADVENTURE_SIZE) {
            throw new IllegalStateException("The current Adventure save is not 512 bytes.");
        }

        try (FileInputStream in = new FileInputStream(source);
             OutputStream out = resolver.openOutputStream(destinationUri, "wt")) {
            if (out == null) throw new IllegalStateException("Could not open export destination.");
            byte[] buffer = new byte[4096];
            int read;
            while ((read = in.read(buffer)) > 0) out.write(buffer, 0, read);
            out.flush();
        }
        return "Adventure save exported successfully.";
    }
}
