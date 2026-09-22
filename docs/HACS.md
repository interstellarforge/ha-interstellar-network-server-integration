# HACS publishing

## One-time setup

1. Set the GitHub repository description and topics.
2. Commit and push the integration.
3. Create a GitHub release for `v0.4.0` after validation passes.

## Add as a custom HACS repository

In Home Assistant:

1. HACS → Integrations
2. Menu → Custom repositories
3. Repository: `https://github.com/interstellarforge/ha-interstellar-network-server-integration`
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
