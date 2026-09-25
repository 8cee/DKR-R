package com.eightcee.dkrrecomp;

import android.content.ContentResolver;
import android.net.Uri;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

final class SaveTransfer {
    static final int ADVENTURE_SIZE = 0x200;
    static final int CONTROLLER_PAK_SIZE = 32 * 1024;
    static final int CONTROLLER_PAK_COUNT = 4;

    private static final byte[] PAK_MAGIC =
            new byte[]{'D','K','R','M','P','K','1',0};
    private static final byte[] BUNDLE_MAGIC =
            new byte[]{'D','K','R','P','O','R','T','S','A','V','E','1',0,0,0,0};
    private static final int BUNDLE_VERSION = 1;
    private static final int BUNDLE_ADVENTURE = 1;
    private static final int BUNDLE_PAK = 2;

    private SaveTransfer() {}

    static File adventureFile(File filesDir) {
        return new File(new File(filesDir, "saves"), "dkr.us.v77.bin");
    }

    static File controllerPakFile(File filesDir, int channel) {
        requireChannel(channel);
        return new File(filesDir, "controller-pak-" + (channel + 1) + ".mpk");
    }

    static String importAdventure(ContentResolver resolver, Uri source, File filesDir) throws Exception {
        byte[] bytes = readExact(resolver, source, ADVENTURE_SIZE, "DKR Adventure save");
        File destination = adventureFile(filesDir);
        File backup = backupIfPresent(filesDir, destination, "adventure-before-android-import", ".bin");
        replaceAtomic(destination, bytes, backup);
        return backup == null
                ? "Adventure save imported successfully."
                : "Adventure save imported. Previous save backed up to " + backup.getName();
    }

    static String exportAdventure(ContentResolver resolver, Uri destinationUri, File filesDir) throws Exception {
        File source = adventureFile(filesDir);
        byte[] bytes = readFileExact(source, ADVENTURE_SIZE, "Adventure save");
        writeUri(resolver, destinationUri, bytes);
        return "Adventure save exported successfully.";
    }

    static String importControllerPak(ContentResolver resolver, Uri source, File filesDir, int channel) throws Exception {
        requireChannel(channel);
        byte[] bytes = readExact(resolver, source, CONTROLLER_PAK_SIZE, "Controller Pak");
        if (!validControllerPak(bytes)) {
            throw new IllegalArgumentException("Selected file is not a valid DKR-R Controller Pak image.");
        }
        File destination = controllerPakFile(filesDir, channel);
        File backup = backupIfPresent(filesDir, destination,
                "controller-pak-" + (channel + 1) + "-before-android-import", ".mpk");
        replaceAtomic(destination, bytes, backup);
        return "Controller Pak " + (channel + 1) + " imported successfully.";
    }

    static String exportControllerPak(ContentResolver resolver, Uri destinationUri, File filesDir, int channel) throws Exception {
        requireChannel(channel);
        File source = controllerPakFile(filesDir, channel);
        byte[] bytes = readFileExact(source, CONTROLLER_PAK_SIZE, "Controller Pak");
        if (!validControllerPak(bytes)) {
            throw new IllegalStateException("Controller Pak " + (channel + 1) + " is not valid.");
        }
        writeUri(resolver, destinationUri, bytes);
        return "Controller Pak " + (channel + 1) + " exported successfully.";
    }

    static String exportBundle(ContentResolver resolver, Uri destinationUri, File filesDir) throws Exception {
        List<Entry> entries = new ArrayList<>();

        File adventure = adventureFile(filesDir);
        if (adventure.isFile() && adventure.length() == ADVENTURE_SIZE) {
            entries.add(new Entry(BUNDLE_ADVENTURE, 0, readFileExact(adventure, ADVENTURE_SIZE, "Adventure save")));
        }

        for (int channel = 0; channel < CONTROLLER_PAK_COUNT; channel++) {
            File pak = controllerPakFile(filesDir, channel);
            if (!pak.isFile() || pak.length() != CONTROLLER_PAK_SIZE) continue;
            byte[] bytes = readFileExact(pak, CONTROLLER_PAK_SIZE, "Controller Pak");
            if (validControllerPak(bytes)) entries.add(new Entry(BUNDLE_PAK, channel, bytes));
        }

        if (entries.isEmpty()) throw new IllegalStateException("No valid Adventure save or Controller Pak is available.");

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(BUNDLE_MAGIC);
        writeLe32(out, BUNDLE_VERSION);
        writeLe32(out, entries.size());
        for (Entry entry : entries) {
            writeLe32(out, entry.kind);
            writeLe32(out, entry.channel);
            writeLe32(out, entry.bytes.length);
            writeLe32(out, imageChecksum(entry.bytes));
            out.write(entry.bytes);
        }
        writeUri(resolver, destinationUri, out.toByteArray());
        return "DKR-R save bundle exported successfully (" + entries.size() + " item(s)).";
    }

    static String importBundle(ContentResolver resolver, Uri source, File filesDir) throws Exception {
        byte[] bundle = readBounded(resolver, source, 64 + ADVENTURE_SIZE +
                CONTROLLER_PAK_COUNT * (32 + CONTROLLER_PAK_SIZE));
        List<Entry> entries = decodeBundle(bundle);

        List<Original> originals = new ArrayList<>();
        for (Entry entry : entries) {
            File destination = entry.kind == BUNDLE_ADVENTURE
                    ? adventureFile(filesDir)
                    : controllerPakFile(filesDir, entry.channel);
            originals.add(new Original(destination,
                    destination.exists() ? Files.readAllBytes(destination.toPath()) : null));
        }

        int committed = 0;
        try {
            for (; committed < entries.size(); committed++) {
                Entry entry = entries.get(committed);
                Original original = originals.get(committed);
                if (original.bytes != null) {
                    String stem = entry.kind == BUNDLE_ADVENTURE
                            ? "adventure-before-bundle-import"
                            : "controller-pak-" + (entry.channel + 1) + "-before-bundle-import";
                    backupBytes(filesDir, original.bytes, stem,
                            entry.kind == BUNDLE_ADVENTURE ? ".bin" : ".mpk");
                }
                replaceAtomic(original.destination, entry.bytes, null);
            }
        } catch (Exception e) {
            for (int i = 0; i < committed; i++) {
                Original original = originals.get(i);
                if (original.bytes == null) original.destination.delete();
                else replaceAtomic(original.destination, original.bytes, null);
            }
            throw new IllegalStateException("Bundle import failed and was rolled back: " + e.getMessage(), e);
        }
        return "DKR-R save bundle imported successfully (" + entries.size() + " item(s)).";
    }

    private static List<Entry> decodeBundle(byte[] bytes) {
        if (bytes.length < 24 || !startsWith(bytes, BUNDLE_MAGIC) || le32(bytes, 16) != BUNDLE_VERSION) {
            throw new IllegalArgumentException("Selected file is not a valid DKR-R save bundle.");
        }
        int count = le32(bytes, 20);
        if (count < 1 || count > 1 + CONTROLLER_PAK_COUNT) {
            throw new IllegalArgumentException("Save bundle entry count is invalid.");
        }

        boolean[] seen = new boolean[1 + CONTROLLER_PAK_COUNT];
        List<Entry> entries = new ArrayList<>();
        int cursor = 24;
        for (int i = 0; i < count; i++) {
            if (cursor + 16 > bytes.length) throw new IllegalArgumentException("Save bundle is truncated.");
            int kind = le32(bytes, cursor);
            int channel = le32(bytes, cursor + 4);
            int size = le32(bytes, cursor + 8);
            int checksum = le32(bytes, cursor + 12);
            cursor += 16;
            if (size < 0 || cursor + size > bytes.length) throw new IllegalArgumentException("Save bundle has an invalid entry size.");

            byte[] payload = new byte[size];
            System.arraycopy(bytes, cursor, payload, 0, size);
            cursor += size;

            int seenIndex;
            if (kind == BUNDLE_ADVENTURE) {
                if (channel != 0 || size != ADVENTURE_SIZE) throw new IllegalArgumentException("Invalid Adventure entry.");
                seenIndex = 0;
            } else if (kind == BUNDLE_PAK) {
                if (channel < 0 || channel >= CONTROLLER_PAK_COUNT ||
                        size != CONTROLLER_PAK_SIZE || !validControllerPak(payload)) {
                    throw new IllegalArgumentException("Invalid Controller Pak entry.");
                }
                seenIndex = 1 + channel;
            } else {
                throw new IllegalArgumentException("Unknown save bundle entry type.");
            }

            if (seen[seenIndex] || checksum != imageChecksum(payload)) {
                throw new IllegalArgumentException("Save bundle checksum or duplicate entry validation failed.");
            }
            seen[seenIndex] = true;
            entries.add(new Entry(kind, channel, payload));
        }
        if (cursor != bytes.length) throw new IllegalArgumentException("Save bundle contains trailing data.");
        return entries;
    }

    private static boolean validControllerPak(byte[] bytes) {
        if (bytes.length != CONTROLLER_PAK_SIZE || !startsWith(bytes, PAK_MAGIC)) return false;
        if (le32(bytes, 8) != 1 || le32(bytes, 16) != imageChecksum(bytes, 16)) return false;

        final int directoryOffset = 256;
        final int entrySize = 64;
        final int maximumFiles = 16;
        final int dataStart = 5 * 256;
        long totalReserved = 0;

        for (int i = 0; i < maximumFiles; i++) {
            int entry = directoryOffset + i * entrySize;
            if (le32(bytes, entry) == 0) continue;
            long size = Integer.toUnsignedLong(le32(bytes, entry + 12));
            long offset = Integer.toUnsignedLong(le32(bytes, entry + 16));
            long reserved = (size + 255L) & ~255L;
            if (size == 0 || offset < dataStart || offset > bytes.length ||
                    size > bytes.length - offset ||
                    reserved > bytes.length - dataStart - totalReserved) return false;
            totalReserved += reserved;
        }
        return true;
    }

    private static int imageChecksum(byte[] bytes) { return imageChecksum(bytes, -1); }

    private static int imageChecksum(byte[] bytes, int clearOffset) {
        int hash = 0x811C9DC5;
        for (int i = 0; i < bytes.length; i++) {
            int value = (clearOffset >= 0 && i >= clearOffset && i < clearOffset + 4) ? 0 : bytes[i] & 0xFF;
            hash ^= value;
            hash *= 0x01000193;
        }
        return hash;
    }

    private static File backupIfPresent(File filesDir, File source, String stem, String extension) throws Exception {
        if (!source.exists()) return null;
        byte[] bytes = Files.readAllBytes(source.toPath());
        return backupBytes(filesDir, bytes, stem, extension);
    }

    private static File backupBytes(File filesDir, byte[] bytes, String stem, String extension) throws Exception {
        File backupDir = new File(filesDir, "save-backups");
        if (!backupDir.exists() && !backupDir.mkdirs()) throw new IllegalStateException("Could not create save backup directory.");
        String stamp = new SimpleDateFormat("yyyyMMdd-HHmmss-SSS", Locale.US).format(new Date());
        File backup = new File(backupDir, stem + "-" + stamp + extension);
        try (FileOutputStream out = new FileOutputStream(backup)) {
            out.write(bytes);
            out.getFD().sync();
        }
        return backup;
    }

    private static void replaceAtomic(File destination, byte[] bytes, File rollback) throws Exception {
        File parent = destination.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) throw new IllegalStateException("Could not create save directory.");
        File temporary = new File(destination.getPath() + ".importing");
        try (FileOutputStream out = new FileOutputStream(temporary)) {
            out.write(bytes);
            out.getFD().sync();
        }
        try {
            Files.move(temporary.toPath(), destination.toPath(),
                    StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (Exception atomicFailure) {
            try {
                Files.move(temporary.toPath(), destination.toPath(), StandardCopyOption.REPLACE_EXISTING);
            } catch (Exception moveFailure) {
                if (rollback != null && rollback.exists()) {
                    Files.copy(rollback.toPath(), destination.toPath(), StandardCopyOption.REPLACE_EXISTING);
                }
                temporary.delete();
                throw moveFailure;
            }
        }
    }

    private static byte[] readExact(ContentResolver resolver, Uri uri, int size, String label) throws Exception {
        byte[] bytes = readBounded(resolver, uri, size);
        if (bytes.length != size) throw new IllegalArgumentException(label + " must be exactly " + size + " bytes.");
        return bytes;
    }

    private static byte[] readBounded(ContentResolver resolver, Uri uri, int maximum) throws Exception {
        try (InputStream in = resolver.openInputStream(uri);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            if (in == null) throw new IllegalStateException("Could not open selected file.");
            byte[] buffer = new byte[8192];
            int total = 0, read;
            while ((read = in.read(buffer)) > 0) {
                total += read;
                if (total > maximum) throw new IllegalArgumentException("Selected file is too large.");
                out.write(buffer, 0, read);
            }
            return out.toByteArray();
        }
    }

    private static byte[] readFileExact(File file, int size, String label) throws Exception {
        if (!file.isFile() || file.length() != size) throw new IllegalStateException("No valid " + label + " is available.");
        return Files.readAllBytes(file.toPath());
    }

    private static void writeUri(ContentResolver resolver, Uri uri, byte[] bytes) throws Exception {
        try (OutputStream out = resolver.openOutputStream(uri, "wt")) {
            if (out == null) throw new IllegalStateException("Could not open export destination.");
            out.write(bytes);
            out.flush();
        }
    }

    private static boolean startsWith(byte[] bytes, byte[] prefix) {
        if (bytes.length < prefix.length) return false;
        for (int i = 0; i < prefix.length; i++) if (bytes[i] != prefix[i]) return false;
        return true;
    }

    private static int le32(byte[] bytes, int offset) {
        return (bytes[offset] & 0xFF) |
                ((bytes[offset + 1] & 0xFF) << 8) |
                ((bytes[offset + 2] & 0xFF) << 16) |
                ((bytes[offset + 3] & 0xFF) << 24);
    }

    private static void writeLe32(ByteArrayOutputStream out, int value) {
        out.write(value & 0xFF);
        out.write((value >>> 8) & 0xFF);
        out.write((value >>> 16) & 0xFF);
        out.write((value >>> 24) & 0xFF);
    }

    private static void requireChannel(int channel) {
        if (channel < 0 || channel >= CONTROLLER_PAK_COUNT) throw new IllegalArgumentException("Invalid Controller Pak channel.");
    }

    private static final class Entry {
        final int kind, channel;
        final byte[] bytes;
        Entry(int kind, int channel, byte[] bytes) { this.kind = kind; this.channel = channel; this.bytes = bytes; }
    }

    private static final class Original {
        final File destination;
        final byte[] bytes;
        Original(File destination, byte[] bytes) { this.destination = destination; this.bytes = bytes; }
    }
}
