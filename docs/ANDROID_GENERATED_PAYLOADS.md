# Generate both Android CPU payloads

The full Android runtime needs N64Recomp output for both supported US DKR
revisions. The ROMs themselves remain local and are never committed or bundled
into the APK.

After preparing the matching v77/v80 ELF and ROM pairs and building the pinned
host `N64Recomp` executable:

```powershell
python scripts/generate_android_payloads.py \
  --n64recomp C:\path\to\N64Recomp.exe \
  --v77-elf C:\path\to\dkr.us.v77.elf \
  --v77-rom C:\path\to\dkr.us.v77.z64 \
  --v80-elf C:\path\to\dkr.us.v80.elf \
  --v80-rom C:\path\to\dkr.us.v80.z64 \
  --output-root build\android-generated
```

The generator resolves `mainproc` from each ELF, detects `.mdebug`, uses the
checked-in v77/v80 recomp policies, and writes:

```text
build/android-generated/v77/
build/android-generated/v80/
```

Those directories can be passed directly to:

```powershell
.\scripts\Build-Android-Full.ps1 \
  -GeneratedV77 build\android-generated\v77 \
  -GeneratedV80 build\android-generated\v80
```

The generated source trees are build artifacts and should remain outside source
control.
