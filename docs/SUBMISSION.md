# Submitting igz_steel to the IngeTrazo extension catalog

IngeTrazo's creator (Ingelibre) runs a community catalog at
<https://github.com/ingelibre/ingetrazo-extensions>, shown inside the app under
**Extensions ▸ Manage extensions…** and at ingetrazo.com/extensiones. The
catalog is a directory, not a store: your code stays in your own repository and
the catalog holds one TOML entry pointing at a fixed release file.

## 1. The code is published (done)

The repository is <https://github.com/dns-0/igz_steel> (branch `main`, tag
`v1.0.0`) and the release <https://github.com/dns-0/igz_steel/releases/tag/v1.0.0>
carries `igz_steel.zip` as its asset. The catalog entry in
`catalog/igz_steel.toml` names that asset and its SHA-256.

Do not re-upload a different zip to that release: the catalog entry carries
the fingerprint and the reviewers read that exact file. A changed package goes
out as a new release (see section 4) with a recomputed hash:

```bash
certutil -hashfile dist\igz_steel.zip SHA256
```

## 2. Take a screenshot

Open IngeTrazo with a few members placed and the Steel toolbar visible, and
save a PNG of about 1200 × 750 pixels, under 600 KB, as `igz_steel.png`.

## 3. Open the pull request on the catalog

1. Go to <https://github.com/ingelibre/ingetrazo-extensions>.
2. In the `extensions/` folder click **Add file ▸ Create new file**, name it
   `igz_steel.toml`, and paste the contents of `catalog/igz_steel.toml` from
   this repository.
3. In the `screenshots/` folder add `igz_steel.png` the same way.
4. Click **Propose changes**, then **Create pull request**.

A bot checks the entry within about a minute: fields complete, licence free,
SHA-256 matching, and the file defining `setup(app)` or a tool. It also reports
network use, program execution and file deletion to the maintainers (igz_steel
does none of these). A maintainer then approves the entry; it appears in the
app's manager labelled **Community**. If a maintainer later reads the code in
full, the entry becomes **Reviewed**.

## 4. Later versions

Bump `__version__` in `igz_steel/__init__.py`, rebuild the zip, tag a new
release (for example `v1.1.0`) with the new asset, and open a pull request on
the catalog that changes only `version`, `download` and `sha256` in
`extensions/igz_steel.toml`. When that pull request comes from the GitHub
account named in `author_url`, the bot publishes it automatically.

## What to mention to the maintainers

- The extension is GPL-3.0-or-later, like IngeTrazo; see `igz_steel/LICENSE`
  and `igz_steel/THIRD-PARTY.md`.
- Dimensional data comes from the AISC Shapes Database v16.0 with AISC's
  disclaimer reproduced; the workbook itself is not redistributed.
- No dependencies beyond IngeTrazo. Tested with 0.5.8 (Extension API 2).
- The repository ships 90 automated tests (`.venv/Scripts/python -m pytest -q`).
