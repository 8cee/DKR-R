package com.eightcee.dkrrecomp;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class ModCompatibilityTest {
    @Test public void comparesNumericVersions() {
        assertTrue(ModCompatibility.compareVersions("0.1.0", "0.2.0") < 0);
        assertTrue(ModCompatibility.compareVersions("1.10.0", "1.2.9") > 0);
        assertEquals(0, ModCompatibility.compareVersions("v1.2", "1.2.0"));
        assertEquals(0, ModCompatibility.compareVersions("1.2.0-beta", "1.2.0"));
    }

    @Test public void mapsSupportedUsRevisions() {
        RomInspector.Result v77 = new RomInspector.Result(
                true, RomInspector.ByteOrder.Z64, 12L * 1024L * 1024L,
                "DIDDY KONG RACING", 0x45, 0, 0, 0, "ok");
        RomInspector.Result v80 = new RomInspector.Result(
                true, RomInspector.ByteOrder.Z64, 12L * 1024L * 1024L,
                "DIDDY KONG RACING", 0x45, 1, 0, 0, "ok");
        assertEquals("v77", ModCompatibility.revisionTag(v77));
        assertEquals("v80", ModCompatibility.revisionTag(v80));
    }

    @Test public void rejectsUnknownOrNonUsRevision() {
        RomInspector.Result unknown = new RomInspector.Result(
                true, RomInspector.ByteOrder.Z64, 12L * 1024L * 1024L,
                "DIDDY KONG RACING", 0x45, 2, 0, 0, "ok");
        RomInspector.Result nonUs = new RomInspector.Result(
                true, RomInspector.ByteOrder.Z64, 12L * 1024L * 1024L,
                "DIDDY KONG RACING", 0x50, 0, 0, 0, "ok");
        assertNull(ModCompatibility.revisionTag(unknown));
        assertNull(ModCompatibility.revisionTag(nonUs));
    }
}
