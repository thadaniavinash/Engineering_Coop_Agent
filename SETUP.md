# Setting up Co-op Scout (about 30 minutes, one time)

You'll need: your GitHub account (thadaniavinash), your Gmail account, and the zip file `Engineering_Coop_Agent.zip`.

## 1. Create the repository
1. Go to https://github.com/new
2. **Repository name:** `Engineering_Coop_Agent`
3. Choose **Public**. Free GitHub Pages sites need a public repository, and public repositories get unlimited free Actions minutes. The email addresses and passwords stay private because they go into encrypted "secrets" (step 4), not into files.
4. Leave "Add a README", ".gitignore" and "license" **unticked**.
5. Click **Create repository**.

## 2. Upload the files
1. Unzip `Engineering_Coop_Agent.zip` on your computer.
2. **Mac only:** open the unzipped folder in Finder and press **Cmd + Shift + .** (period). This shows hidden items, so the `.github` folder becomes visible. It contains the daily schedule and must be uploaded.
3. On the new repository page, click the link **"uploading an existing file"**. If you don't see it, use **Add file → Upload files**.
4. Open the unzipped folder, select **everything inside it** (Cmd + A or Ctrl + A), including `.github`, and drag it onto the upload area. Drag the *contents*, not the folder itself.
5. Wait until all files are listed, then click **Commit changes**.
6. Check that the repository's front page shows the folders `.github`, `agent`, `claude`, `config`, `docs` and `tests`. If `.github` is missing, repeat steps 2–5 with just the `.github` folder.

## 3. Let the daily job save its results
1. In the repository, open **Settings → Actions → General**.
2. Under **Workflow permissions**, choose **Read and write permissions** and click **Save**.

## 4. Set up email (Gmail app password)
Gmail needs an "app password" before a program can send mail. Your normal password won't work, and you shouldn't use it here.
1. Make sure 2-Step Verification is on: https://myaccount.google.com/security
2. Go to https://myaccount.google.com/apppasswords, type the name `Co-op Scout`, and click **Create**.
3. Copy the 16-letter password it shows. You'll only see it once.
4. In the repository, open **Settings → Secrets and variables → Actions → New repository secret** and add these three secrets, one at a time:

| Name | Secret |
|---|---|
| `GMAIL_ADDRESS` | `thadaniavinash@gmail.com` |
| `GMAIL_APP_PASSWORD` | the 16-letter app password |
| `EMAIL_TO` | `thadaniavinash@gmail.com,vivaanthadani@gmail.com` |

## 5. (Optional, recommended) Free job-aggregator keys
These catch employers that aren't on the company list. Without them the agent still runs, but these two sources show "not set up".
- **Adzuna:** sign up at https://developer.adzuna.com/signup, open your dashboard, and add the secrets `ADZUNA_APP_ID` and `ADZUNA_APP_KEY`.
- **Jooble:** request a key at https://jooble.org/api/about and add it as the secret `JOOBLE_API_KEY`.

## 6. Turn on the website
1. Open **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **Deploy from a branch**.
3. For **Branch**, choose `main` and the folder `/docs`, then click **Save**.
4. After a minute or two the site is live at **https://thadaniavinash.github.io/Engineering_Coop_Agent/**. It says "Waiting for the first run" until step 7 is done.

## 7. Run it for the first time
1. Open the **Actions** tab. If GitHub asks, click **I understand my workflows, go ahead and enable them**.
2. Click **Daily co-op search** in the left list, then **Run workflow → Run workflow**.
3. The run takes about 10–20 minutes. A green tick means it finished. Refresh the website to see the listings. The first email lists everything found, and later emails list only new postings.
4. From now on it runs by itself every morning.

## 8. Weekly Claude summaries (give Claude limited access)
1. Go to https://github.com/settings/personal-access-tokens/new (a "fine-grained" token).
2. **Token name:** `Co-op Scout weekly Claude`. **Expiration:** choose a custom date, e.g. one year from now.
3. **Repository access:** choose **Only select repositories** → `Engineering_Coop_Agent`.
4. **Permissions → Repository permissions → Contents:** choose **Read and write**. Leave everything else as it is.
5. Click **Generate token**, copy it, and send it to Claude in the Cowork chat. Claude then sets up the weekly task.
   The token only works on this one repository and can only edit files. You can delete it any time on the same settings page.

## If something goes wrong
- **Red X on a run:** click the run, then the **search** step, to see the log. You can send a screenshot to Claude.
- **A site shows "error" or "unrecognised"** under Sources on the website: the weekly Claude task tries to fix these. Until it does, those sites are listed under "Check by hand".
- **No email arrived:** check the spam folder, then double-check the three email secrets. The app password must be the 16-letter one.
