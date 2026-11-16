# Put Skills Radar online (free)

You'll end up with:
- **A public dashboard** at `https://<your-name>-skills-radar.streamlit.app` to share on your resume and LinkedIn.
- **GitHub Actions** collecting new postings **every morning** and emailing you the jobs posted in the last 24 hours
  (or a weekly email on Mondays: set `DIGEST_FREQUENCY = "weekly"` in `config.py`).

Only the **code** goes into the repo. The whole `data/` folder (job database, your tracker, your resume)
is excluded by `.gitignore`. The daily job stores the job database as a **release file** named "data",
which it replaces each day, so the repo stays small. The public app downloads that file and hides the
tracker and save buttons.

---

## 1. Put the code on GitHub (about 5 minutes)

1. Go to **github.com → New repository**, name it `skills-radar`, and choose **Public**. Don't add a README.
2. In Terminal, inside your `skills-radar` folder:

```bash
cd "/Users/hetvishah/Desktop/Projects/Skills Radar/skills-radar"
git init
git add .
git status                             # check: NOTHING from data/ is listed (no radar.db, tracker.db, resume)
git commit -m "Skills Radar"
git branch -M main
git remote add origin https://github.com/hetvishah18-bit/skills-radar.git
git push -u origin main
```

If `git push` asks for a password, use a GitHub **personal access token**, not your GitHub
password (GitHub → Settings → Developer settings → Personal access tokens). You can also install
GitHub Desktop and publish from there.

## 2. Turn on the daily job (about 5 minutes)

In your repo on GitHub: **Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Value | Needed for |
|---|---|---|
| `GMAIL_ADDRESS` | the Gmail that sends the digest | email |
| `GMAIL_APP_PASSWORD` | a Gmail **App Password** (see below) | email |
| `DIGEST_TO` | where to send it (optional; defaults to GMAIL_ADDRESS) | email |
| `RESUME_TEXT` | *(skip)*: only needed if you turn on `DIGEST_USE_RESUME` in config.py | optional |

**Gmail App Password:** turn on 2-Step Verification for your Google account, then go to
myaccount.google.com → search "App passwords" → create one named "Skills Radar" → copy the 16 letters.
It's not your normal password and can be deleted at any time.

Secrets are encrypted. They don't show in the code or logs, and other people can't read them even
though the repo is public.

Then: **Actions tab → "Daily collect + digest" → Run workflow** to test it now. The first run takes
about 15–30 minutes (it checks ~1,500 companies). Afterwards you'll see a **Releases → "Job data"** entry
on the repo's main page containing `radar.db.gz`, plus a digest email if you set up Gmail.
From then on it runs every morning at about 6 AM Pacific.

Skip the email secrets if you only want daily collection. The email step is skipped automatically.

## 3. Deploy the dashboard (about 5 minutes)

1. Go to **share.streamlit.io** and sign in with GitHub.
2. Click **Create app → "Yup, I have an app"**.
3. Repository `hetvishah18-bit/skills-radar`, branch `main`, main file `app.py`.
4. App URL: choose something like `hetvi-skills-radar`.
5. Open **Advanced settings**:
   - Python version: **3.12**
   - Secrets: paste these two lines. The first hides the personal tab; the second tells the app where
     to download the daily job data:
     ```toml
     RADAR_PUBLIC = "1"
     RADAR_DATA_URL = "https://github.com/hetvishah18-bit/skills-radar/releases/download/data/radar.db.gz"
     ```
6. Click **Deploy**. Run step 2's workflow at least once first, so the data file exists. The app
   re-downloads the data every 6 hours, so it stays current on its own.

## Your two versions

| | On your Mac (`python -m streamlit run app.py`) | Online (streamlit.app) |
|---|---|---|
| Dashboard, trends, filters | ✅ | ✅ |
| Job match (upload resume) | ✅ | ✅ (the resume stays in the visitor's session and isn't saved) |
| 📋 My applications tracker | ✅ | hidden |
| Save buttons | ✅ | hidden |

Your Mac keeps its own `data/radar.db` from `python collect.py`. The online data lives in the release
file; download `radar.db.gz` from the repo's Releases page if you ever want it locally.

## Troubleshooting

- **The Actions run failed at "Save today's data"**: go to Settings → Actions → General → Workflow
  permissions and choose "Read and write permissions", then run it again.
- **No email arrives**: check your spam folder; make sure you used the App Password, not your Gmail password.
- **The app says "Couldn't download the job data"**: the workflow hasn't finished a run yet (step 2), or
  the `RADAR_DATA_URL` secret has a typo.
- **GitHub paused the schedule**: GitHub pauses scheduled jobs in repos with no activity for 60 days.
  If that happens, click "Enable workflow" in the Actions tab.
