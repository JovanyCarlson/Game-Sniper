# GameSniper — Free encrypted Roblox + Steam breakout monitor

GameSniper polls public Roblox and Steam game statistics through scheduled GitHub Actions, calculates growth across 15m / 1h / 6h / 24h, sends private Discord webhook embeds, and hosts a dark dashboard on GitHub Pages. **The repository and website are public, but all actual scan results and alert history are encrypted with AES-256-GCM.** Without your private 256-bit key, visitors only see a locked dashboard or fictional demo mode. Public code can still be copied; this protects YOUR observations, not exclusive ownership of the source code.

## Security model — READ BEFORE ACTIVATING

- **Never commit** your Discord webhook, encryption key, access tokens, `.env` files, or plaintext player history.
- GitHub Actions secrets `GAMESNIPER_STATE_KEY` and `DISCORD_WEBHOOK_URL` are injected into only the scheduled scanner job. The public website doesn't contain either secret.
- The scanner encrypts both the saved history and the dashboard JSON into `docs/secure.enc.json` **before** it commits anything. There is no unencrypted `docs/data.json` or `data/state.json` in the repository.
- The browser decrypts the encrypted JSON locally using Web Crypto. The key is held only in the current tab's memory and isn't stored in cookies, localStorage, query parameters, or the GitHub Pages server.
- Do not lose the encryption key: encrypted history cannot be recovered without it. Never replace the existing key unless intentionally resetting history.
- A public GitHub Pages site is not the same as a private authenticated site. Anyone can see the lock page and download ciphertext; only someone with the strong random key should be able to decrypt actual results. Never tell others the key.
- GitHub Actions schedules can be delayed or skipped, and source providers can change APIs. This is **not** a guaranteed instant-alert system.

## Setup (you only need your GitHub account)

1. Go to your repository **Settings → Pages**, and set **Source = GitHub Actions**. A separate `site.yml` workflow publishes the locked website after code commits; the scanner also republishes after scans.
2. Open the published GitHub Pages dashboard with HTTPS (shown in Settings → Pages). On the unlock screen, click **Generate a secure new key locally**. Copy and privately save the entire generated key.
3. In your repository **Settings → Secrets and variables → Actions → New repository secret**, create a secret named exactly `GAMESNIPER_STATE_KEY` and paste your new key. This is the 32-byte random AES key encoded as base64, not a personal password you choose.
4. In Discord, create a webhook for a channel accessible only to you; copy its URL. In GitHub Actions secrets, create `DISCORD_WEBHOOK_URL` and paste the URL. **Never commit or share that URL.**
5. In GitHub **Actions**, run **GameSniper - encrypted 24/7 radar → Run workflow** once. After a successful run, the workflow commits only `docs/secure.enc.json`. Scheduled scans aim for every 5 minutes while the repository remains eligible for scheduled workflows.
6. Refresh the dashboard, paste the same private key into the unlock form, and view live game statistics. Keep your PC off: GitHub runners perform scheduled scans.

If you want a private watchlist (not visible in `config.json`), add another optional GitHub Actions secret named `GAMESNIPER_PRIVATE_WATCHLIST_JSON` with e.g. `{"roblox_universe_ids":[],"roblox_place_ids":[],"steam_app_ids":[]}` and change only those arrays.

## Discord alert fields

Every qualifying alert has a **clickable game name**, the latest **active player count**, Roblox **creation date** or Steam **release date**, Roblox **lifetime visits** (Steam total store visits are not public), Roblox **like approval ratio** or Steam **positive review ratio/count**, and **15m / 1h / 6h / 24h growth**. The priority window is selected in `config.json`. Discord webhooks cannot provide a live timeframe picker; all four windows appear in the same embed. Switch timeframes interactively on the dashboard.

## What other people can see

| Resource | Public visitors |
| --- | --- |
| GitHub repository, source and dashboard code | Yes |
| Dashboard login/lock screen and fictional `?demo=1` mode | Yes |
| `docs/secure.enc.json` encrypted bytes | Yes, **not decryptable without your key** |
| Your decrypted history and alert log | No, if your strong key stays secret |
| GitHub Actions secrets / Discord webhook / encryption key | No, unless credentials or workflow security are compromised |
| Your own running GitHub Actions workflow or your Discord messages | No, without your account/channel permissions |

## Technology and limitations

GitHub Actions, Python 3.12, `httpx`, `beautifulsoup4`, `cryptography`, AES-256-GCM, and browser Web Crypto. The frontend is static: no database server or monthly hosting service. Public runners are free within GitHub's terms; excessive polling may hit vendor rate limits. Scans collect history starting when you turn on the workflow. Steam does not publish lifetime visits, wishlists, or exact app creation dates; the publicly visible store release date is used. GitHub Pages remains a *public URL*, with encrypted content rather than account-based authorization. A public codebase can always be forked and independently run by someone else.

To run tests locally: `python -m pip install -r requirements.txt` then `python -m unittest discover -s tests -v`.

No affiliations with Roblox, Steam, Valve, GitHub, or Discord.
