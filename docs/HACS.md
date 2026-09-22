# HACS publishing

## One-time setup

1. Create a public GitHub repository named `home-assistant-interstellar-network`.
2. Run:
   ```bash
   ./scripts/configure-repository.sh YOUR_GITHUB_USERNAME
   ```
3. Commit and push the repository.
4. Create a GitHub release for `v0.3.0`.

## Add as a custom HACS repository

In Home Assistant:

1. HACS → Integrations
2. Menu → Custom repositories
3. Repository: `https://github.com/YOUR_GITHUB_USERNAME/home-assistant-interstellar-network`
4. Category: Integration
5. Download Interstellar Network
6. Restart Home Assistant

After that, new GitHub releases appear as HACS updates.

## Publishing a new version

```bash
./scripts/release.sh 0.4.0
git push origin main
git push origin v0.4.0
```

Create the matching GitHub Release. The release workflow attaches a manual-install ZIP automatically.
