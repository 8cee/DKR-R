# Android mod server contract

The Android launcher includes an in-app **Mods / Hacks** manager backed by a JSON catalog. The default development catalog lives at `android/mod-server/catalog.json` and the app points at the raw `android` branch catalog through `BuildConfig.MOD_SERVER_URL`.

A catalog has `schemaVersion`, `generatedAt`, and a `mods` array. Schema version 1 supports:

- `id`: stable lowercase identifier
- `name`
- `version`
- `category`: translations, textures, characters, tracks, gameplay, or ui
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

The launcher can refresh the catalog, show installed versions, install a new mod, update/reinstall an existing mod, and remove an installed mod. Installed metadata is written to `mod.json` beside the unpacked payload so the launcher can compare the installed catalog version with the current server entry.

The client rejects an unsupported catalog schema, duplicate IDs, invalid categories, non-HTTPS download URLs, malformed SHA-256 values, oversized catalog responses, and declared archives above 512 MiB.

Downloads are always SHA-256 verified. If `size` is supplied, the downloaded byte count must also match it. ZIP extraction rejects paths that escape the staging directory, limits archives to 10,000 entries, and caps expanded data at 1 GiB. Activation uses a staging directory plus a temporary previous-version directory so a failed replacement restores the old install instead of leaving a partially installed mod.

App-private root:

`/data/user/0/com.eightcee.dkrrecomp/files/mods/`

Installed layout:

`mods/<category>/<id>/`

The app must never distribute the DKR ROM or copyrighted game assets through the mod service. Catalog packages should contain only redistributable mod content and metadata.

## Remaining compatibility work

The schema already reserves `gameRevisions`, `minAppVersion`, `dependencies`, and `conflicts`. The launcher currently parses these fields but does not yet resolve dependency graphs or block installs by active ROM revision/app version. Those checks should be added before publishing a public production catalog with interdependent mods.
