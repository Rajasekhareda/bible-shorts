# Daily Bible Verse Shorts — Full Automation

Every day at ~5:00 AM IST, this pipeline:
1. Picks the next unused verse (Telugu + English) from `verses.json`
2. Renders a 1080x1920 vertical video: soft animated gradient background,
   the Telugu text fading/sliding in, then the English text, then the
   reference — with soft background music underneath
3. Uploads it straight to your YouTube channel as a public Short
4. Marks that verse "used" so it's never repeated

It runs on **GitHub Actions** (free, no computer of yours needs to stay on).

---

## One-time setup (about 20-30 minutes)

### 1. Create the repo
- Create a new **private** GitHub repository.
- Upload/push everything in this folder to it.

### 2. Get YouTube API access (OAuth)
YouTube uploads need your channel's permission via Google's API — this is
a one-time authorization, not a password you store anywhere.

1. Go to https://console.cloud.google.com/ → create a new project.
2. **APIs & Services → Library** → enable **"YouTube Data API v3"**.
3. **APIs & Services → OAuth consent screen** → set up as "External", add
   your own Google account as a Test User (this keeps it private, no
   Google review needed).
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   → Application type: **Desktop app** → Create → **Download JSON**.
   Rename the downloaded file to `client_secret.json` and put it in this
   project folder (do NOT commit it to GitHub — it's already in `.gitignore`).
5. On your own computer, install the auth library and run the one-time
   script:
   ```bash
   pip install google-auth-oauthlib google-auth
   python3 scripts/get_refresh_token.py
   ```
   A browser window opens — log in with the Google account that owns
   your YouTube channel and approve access. The script prints three
   values: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.

6. In your GitHub repo: **Settings → Secrets and variables → Actions →
   New repository secret**. Add all three as separate secrets with those
   exact names.

You will never need to log in again — the refresh token lets the
automation upload on your behalf indefinitely (unless you revoke access).

### 3. Add background music
Add 2-3 **royalty-free / no-copyright** soft instrumental loops (30-60
seconds each is enough, the script loops them) as `.mp3` files into
`assets/music/`. Good free sources:
- YouTube Audio Library (studio.youtube.com → Audio Library) — filter by
  "Ambient" or "Calm", download as mp3
- Pixabay Music (pixabay.com/music) — search "soft piano" or "ambient"

The script picks one at random each day, so 3-5 tracks keeps it varied.

### 4. Add verses
Edit `verses.json` and paste in verses, Telugu and English side by side,
following the existing format. Add as many as you like — the queue never
runs dry as long as you keep topping it up. The workflow will fail loudly
(and GitHub will email you) if the queue is ever empty, rather than
silently repeating a verse.

### 5. Test it manually before trusting the schedule
In your repo: **Actions tab → "Daily Bible Verse Short" → Run workflow**.
Watch it run. Check:
- The render step succeeds
- The video actually appears on your channel (starts as **public** — see
  note below if you'd rather review before it's live)
- `verses.json` gets committed back with that verse marked `used: true`

---

## Notes & things worth knowing

- **Timing**: the cron is set to `0 23 * * *` UTC = 5:00 AM IST. If you're
  not in IST, or want a different local time, change the cron line in
  `.github/workflows/daily_short.yml` (cron times are always UTC).
- **Publishes immediately as public.** If you'd rather have it upload as
  **private/scheduled** so you can preview each morning before it goes
  live, tell me and I'll switch `upload_youtube.py` to use
  `privacyStatus: "private"` + a `publishAt` timestamp instead — YouTube
  will then auto-publish it at the exact time you choose.
- **Failure notifications**: GitHub automatically emails the repo owner
  when a scheduled workflow run fails, so you'll know the same morning if
  something needs attention (empty verse queue, expired token, etc.).
- **Video duration** auto-scales with verse length (16-45 seconds), so
  longer verses don't get cut off or feel rushed.
- **No copyrighted visuals** are used — the background is a generated
  gradient, not stock footage, so there's no copyright-strike risk on
  the visual side. Just make sure your music is genuinely royalty-free.
- **Costs**: GitHub Actions is free for private repos up to 2,000
  minutes/month on the free tier; this job takes roughly 2-3 minutes/day,
  well within that.

## File overview
```
verses.json                        <- your verse queue (edit this regularly)
assets/music/*.mp3                 <- your royalty-free music loops (you add these)
scripts/generate_video.py          <- renders the video
scripts/upload_youtube.py          <- uploads to YouTube
scripts/get_refresh_token.py       <- one-time local auth helper
.github/workflows/daily_short.yml  <- the daily schedule
```
