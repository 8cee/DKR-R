package com.eightcee.dkrrecomp;

import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

final class RomInspector {
    enum ByteOrder { Z64, V64, N64, UNKNOWN }

    static final class Result {
        final boolean candidate;
        final ByteOrder byteOrder;
        final long size;
        final String title;
        final int country;
        final int revision;
        final long crc1;
        final long crc2;
        final String message;

        Result(boolean candidate, ByteOrder byteOrder, long size, String title,
               int country, int revision, long crc1, long crc2, String message) {
            this.candidate = candidate;
            this.byteOrder = byteOrder;
            this.size = size;
            this.title = title;
            this.country = country;
            this.revision = revision;
            this.crc1 = crc1;
            this.crc2 = crc2;
            this.message = message;
        }

        String describe() {
            return message + "\nContainer: " + byteOrder +
                    "\nSize: " + size +
                    "\nHeader title: " + title +
                    String.format(Locale.US, "\nCRC1/CRC2: %08X / %08X", crc1, crc2) +
                    String.format(Locale.US, "\nCountry/revision: %02X / %02X", country, revision);
        }
    }

    private RomInspector() {}

    static Result inspect(File file) {
        final long expected = 12L * 1024L * 1024L;
        byte[] header = new byte[0x40];
        try (FileInputStream in = new FileInputStream(file)) {
            int offset = 0;
            while (offset < header.length) {
                int n = in.read(header, offset, header.length - offset);
                if (n < 0) break;
                offset += n;
            }
            if (offset != header.length) {
                return invalid(file.length(), ByteOrder.UNKNOWN, "File is too small.");
            }
        } catch (Exception e) {
            return invalid(file.length(), ByteOrder.UNKNOWN, "Could not inspect ROM: " + e.getMessage());
        }

        ByteOrder order = detect(header);
        if (order == ByteOrder.UNKNOWN) {
            return invalid(file.length(), order, "Not a recognized N64 ROM container.");
        }
        canonicalizeHeader(header, order);

        String title = new String(header, 0x20, 20, StandardCharsets.US_ASCII).trim();
        int country = header[0x3E] & 0xFF;
        int revision = header[0x3F] & 0xFF;
        long crc1 = be32(header, 0x10);
        long crc2 = be32(header, 0x14);

        boolean looksLikeDkr = title.toUpperCase(Locale.ROOT).contains("DIDDY KONG RACING");
        boolean correctSize = file.length() == expected;
        boolean candidate = looksLikeDkr && correctSize;
        String message;
        if (!correctSize) {
            message = "Unsupported ROM size. DKR-R expects the 12 MiB retail ROM.";
        } else if (!looksLikeDkr) {
            message = "The N64 header does not identify Diddy Kong Racing.";
        } else {
            message = "DKR retail ROM candidate detected. The native DKR-R runtime will perform the final XXH3 revision check before launch.";
        }
        return new Result(candidate, order, file.length(), title, country, revision, crc1, crc2, message);
    }

    private static Result invalid(long size, ByteOrder order, String message) {
        return new Result(false, order, size, "", 0, 0, 0, 0, message);
    }

    private static ByteOrder detect(byte[] h) {
        int a=h[0]&255,b=h[1]&255,c=h[2]&255,d=h[3]&255;
        if (a==0x80 && b==0x37 && c==0x12 && d==0x40) return ByteOrder.Z64;
        if (a==0x37 && b==0x80 && c==0x40 && d==0x12) return ByteOrder.V64;
        if (a==0x40 && b==0x12 && c==0x37 && d==0x80) return ByteOrder.N64;
        return ByteOrder.UNKNOWN;
    }

    private static void canonicalizeHeader(byte[] h, ByteOrder order) {
        if (order == ByteOrder.V64) {
            for (int i=0;i<h.length;i+=2) {
                byte t=h[i]; h[i]=h[i+1]; h[i+1]=t;
            }
        } else if (order == ByteOrder.N64) {
            for (int i=0;i<h.length;i+=4) {
                byte t=h[i]; h[i]=h[i+3]; h[i+3]=t;
                t=h[i+1]; h[i+1]=h[i+2]; h[i+2]=t;
            }
        }
    }

    private static long be32(byte[] h, int o) {
        return ((long)(h[o]&255)<<24)|((long)(h[o+1]&255)<<16)|((long)(h[o+2]&255)<<8)|(long)(h[o+3]&255);
    }
}
