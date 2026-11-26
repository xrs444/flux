# Supernote pipeline

Manta -> Supernote Private Cloud (`supernote.xrs444.net`) -> note-router ->
- `Note/Personal/**` -> `obsidian/Supernote/**.md` + PDF (existing Syncthing -> Obsidian)
- `Note/Work/**`     -> `supernote-work-outbox/` PDF + HTML (share to OneNote manually)
- `TODO ...` lines   -> Vikunja tasks (one-way, hash-deduped)

Raw `.note` files are copied to `/sync/raw-backup` before any parsing.

## Before enabling
1. Create + seal `supernote-secrets` (keys: `mysql-root-password`, `mysql-user`,
   `mysql-password`, `redis-password`, `vikunja-token`) into
   `sealedsecret-supernote-secrets.yaml`, uncomment it in `kustomization.yaml`.
   (Fish: use pipes, not `<()`.)
2. Create a Vikunja API token; set `VIKUNJA_PROJECT_ID` in `supernote.yaml`.
3. Push `note-router/` (CI builds `ghcr.io/xrs444/note-router`), pin the digest.
4. Add `./supernote` to `apps/services/kustomization.yaml`.
5. Register the Supernote account (needs working mail per Supernote's manual),
   then log in from the Manta against `supernote.xrs444.net`.
6. Syncthing: reuses the existing instance (`apps/system-services/syncthing`).
   Personal notes land in `obsidian/Supernote/` inside the already-synced
   Obsidian folder — nothing to do. For Work, add a folder
   `/var/syncthing/xrs444/supernote-work-outbox` (e.g. id `supernote-work`)
   to its `config/folder.json` + reconcile script, shared with the iPhone only.

## Unverified (check on first start)
- notelib port / how supernote-service addresses it (Service assumes 8080).
- supernote-service env var names and the `data/` layout it writes under.
- socket.io path split in the IngressRoute.
- NFS write access for uid 1000 under `xrs444/`; note-router's keyword/title extraction (best effort).
