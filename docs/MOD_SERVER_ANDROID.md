# Android mod server contract

The Android launcher includes an in-app **Mods / Hacks** manager backed by a JSON catalog. The default development catalog lives at `android/mod-server/catalog.json` and the app points at the raw `android` branch catalog through `BuildConfig.MOD_SERVER_URL`.

A catalog has `schemaVersion`, `generatedAt`, and a `mods` array. Schema version 1 supports:

- `id`: stable lowercase identifier
- `name`
- `version`
- `category`: translations, textures, characters, tracks, gameplay, or ui
- `installTarget`: optional activation adapter: `library` (default), `custom-track`, `texture-pack`, `legacy-track`, or `legacy-character`
- `description`
- `author`
- `downloadUrl`
- `sha256`
- `size`
- `gameRevisions`: e.g. v77/v80
- `minAppVersion`
- `dependencies`
- `conflicts`

## Android client behavior

The launcher automatically refreshes the catalog, shows installed versions, install/update state, app/ROM compatibility, dependencies and conflicts, and can remove installed mods. Installed metadata is written to `mod.json` beside the unpacked payload so the launcher can compare the installed catalog version with the current server entry and evaluate dependency relationships.

The client rejects an unsupported catalog schema, duplicate IDs, invalid categories, invalid ROM revision tags, malformed dependency/conflict IDs, self-dependencies/self-conflicts, duplicate relationship entries, non-HTTPS download URLs, malformed SHA-256 values, oversized catalog responses, and declared archives above 512 MiB.

Downloads are always SHA-256 verified. If `size` is supplied, the downloaded byte count must also match it. ZIP extraction rejects paths that escape the staging directory, limits archives to 10,000 entries, and caps expanded data at 1 GiB. Activation uses a staging directory plus a temporary previous-version directory so a failed replacement restores the old install instead of leaving a partially installed mod.

App-private root:

`/data/user/0/com.eightcee.dkrrecomp/files/catalog-mods/`

Installed layout:

`catalog-mods/<category>/<id>/`

The app must never distribute the DKR ROM or copyrighted game assets through the mod service. Catalog packages should contain only redistributable mod content and metadata.

## Compatibility rules

If `gameRevisions` is present, the launcher requires a supported selected US ROM and only enables installation when its revision is listed. US revision 0 maps to DKR-R `v77`; revision 1 maps to `v80`. `minAppVersion` is compared against the Android app version, all IDs in `dependencies` must already be installed, and any installed ID listed in `conflicts` blocks installation.

Removal is also dependency-aware: a mod cannot be removed while another installed mod lists it as a dependency. Version-constrained dependencies and automatic dependency installation are intentionally not part of schema version 1.


## Runtime activation boundary

The catalog library is intentionally separate from the native runtime's `mods/` directory. DKR-R reserves `mods/` for native/librecomp-managed mod formats, and custom tracks and texture packs have their own managed stores. A catalog download is therefore treated as verified library content until an explicit installer adapter activates it into the correct native subsystem. This avoids making an arbitrary ZIP look like a valid runtime mod merely because it contains a `mod.json`.


For `custom-track` and `texture-pack`, the verified original ZIP is retained inside the catalog library and handed to DKR-R's native installer. `legacy-track` and `legacy-character` packages are passed through DKR-R's reviewed legacy import pipeline, which verifies the user's original ROM, extracts only supported asset content, prepares it in the native legacy library, and enables the single reviewed item represented by the catalog package. These activation modes are available only in a full-runtime APK. Generic `library` packages remain isolated and are not treated as active runtime mods.


## Native removal and updates

When a catalog package activates into a native subsystem, the assigned native ID is persisted in the catalog copy's `mod.json`. Removal first asks the native subsystem to uninstall that exact ID and only deletes the catalog copy after native removal succeeds. Custom-track removal also removes its managed track-owned HD texture pack. Texture-pack updates deactivate the previous native pack after the replacement has activated successfully, avoiding duplicate managed packs.

If a download succeeded but native activation never completed, the catalog copy has no native ID and can still be removed safely without calling a native uninstaller.


## Failed update recovery

Downloaded catalog version and active native version are tracked separately. If a replacement package downloads but its native activation fails, the catalog metadata records the activation error and retains the previous native target, native ID, and active version. The launcher therefore continues to know exactly which native content is active, can remove it safely, and can retry the replacement later without orphaning the previous installation.


## Activation target/category rules

Native activation targets are intentionally narrow:

- `custom-track` and `legacy-track` require category `tracks`.
- `legacy-character` requires category `characters`.
- `texture-pack` requires category `textures`.
- `translations`, `gameplay`, and `ui` packages currently use `library` unless a future DKR-R runtime adapter explicitly owns their format.

The legacy importer never executes patched ROM code. It analyzes patches against the user's verified US v1.0/v1.1 ROM and only prepares the reviewed track/character asset forms supported by DKR-R.

## Storage migration

Early Android catalog builds used `files/mods/<category>/<id>`, which conflicts with DKR-R's native mod namespace. Startup now migrates only directories whose `mod.json` matches the catalog signature (valid id/category plus HTTPS download URL and SHA-256) into `files/catalog-mods/`. Native `mods/legacy` content and unrelated runtime-owned directories are never migrated.
