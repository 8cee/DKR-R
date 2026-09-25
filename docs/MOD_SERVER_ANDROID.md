# Android mod server contract

The Android client reads a JSON catalog. The default development catalog lives at `android/mod-server/catalog.json`.

A catalog has `schemaVersion`, `generatedAt`, and a `mods` array. Each mod may provide:

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

Production installation must verify SHA-256 before unpacking and must reject archive paths that escape the target mod directory. Mods should be installed atomically and retain the previous version for rollback.

App-private root:

`/data/user/0/com.eightcee.dkrrecomp/files/mods/`

The app must never distribute the DKR ROM or copyrighted game assets through the mod service.
