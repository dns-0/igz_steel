# Submitting igz_steel to the IngeTrazo extension catalog

IngeTrazo's creator (Ingelibre) runs a community catalog at
<https://github.com/ingelibre/ingetrazo-extensions>, shown inside the app under
**Extensions ▸ Manage extensions…** and at ingetrazo.com/extensiones. The
catalog is a directory, not a store: your code stays in your own repository and
the catalog holds one TOML entry pointing at a fixed release file.

## 1. Publish the code in your own GitHub repository

1. Create an empty public repository on GitHub named `igz_steel` (any host
   works; GitHub keeps the update path automatic later).
2. From this folder, push the branch and the tag:

```bash
git remote add origin https://github.com/YOUR-GITHUB-USER/igz_steel.git
git push -u origin feature/igz-steel
git push origin v1.0.0
```

   (Merge `feature/igz-steel` into `main` first if you prefer `main` to be the
   default branch; the tag is what matters to the catalog.)

3. On GitHub open **Releases ▸ Draft a new release**, choose tag `v1.0.0`,
   and attach `dist/igz_steel.zip` as a release asset. Publish the release.
   The asset address will be
   `https://github.com/YOUR-GITHUB-USER/igz_steel/releases/download/v1.0.0/igz_steel.zip`.

Do not rebuild the zip after this step: the catalog entry carries its SHA-256
and the reviewers read that exact file. If you do rebuild it, recompute the
hash with:

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
   this repository with `YOUR-GITHUB-USER` replaced.
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
