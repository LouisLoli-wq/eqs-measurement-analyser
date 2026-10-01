# Deployment

Four ways to run this, in order of how much customer data leaves your control.
Pick deliberately: measurement files show when a site is occupied and what
plant is running.

| Option | Data location | Effort | Good for |
|---|---|---|---|
| 1 · One laptop | that laptop | minutes | one person |
| 2 · An office PC on the LAN | that PC | ~15 min | the team |
| 3 · Azure App Service | your M365 tenant | ~1 hour | client work, remote access |
| 4 · Streamlit Community Cloud | Streamlit's servers | ~10 min | demos only |

**Nothing here is enabled automatically.** Every option is a decision to make
after reviewing the repository.

---

## Option 1 — One laptop

```bash
git clone https://github.com/LouisLoli-wq/eqs-measurement-analyser.git
cd eqs-measurement-analyser
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`.

---

## Option 2 — An office PC, shared over the LAN

Set it up as in option 1, then:

```bash
streamlit run app.py --server.address=0.0.0.0 --server.port=8501
```

1. Find the PC's address: `ipconfig` on Windows, the IPv4 line.
2. Send colleagues `http://<that-address>:8501`. Nothing for them to install.
3. Allow the port through Windows Firewall, once, as an administrator:
   ```
   netsh advfirewall firewall add rule name="EQS Analyser" ^
       dir=in action=allow protocol=TCP localport=8501
   ```

That PC must stay on and awake. Everyone shares one server, so analyses queue;
each person's uploads stay in their own session folder.

**No login.** Anyone who can reach the PC on the network can use it. Fine
inside an office. Do not port-forward it to the internet.

---

## Option 3 — Azure App Service

Keeps customer data inside the tenant you already run.

1. **Azure Portal** → Create a resource → **Web App**.
2. Publish: **Code**. Runtime: **Python 3.11**. Region: nearest. Plan: **B1**
   or better — the free tier will time out on a full figure run.
3. **Deployment Center** → source **GitHub** → authorise → pick
   `LouisLoli-wq/eqs-measurement-analyser`, branch `main`. Azure writes the
   workflow file itself.
4. **Configuration** → **General settings** → Startup Command:
   ```
   python -m streamlit run app.py --server.port 8000 --server.address 0.0.0.0
   ```
5. **Configuration** → **Application settings** → add
   `SCM_DO_BUILD_DURING_DEPLOYMENT` = `true`. Save and restart.
6. **Authentication** → **Add identity provider** → **Microsoft** → restrict
   to your tenant. This is what gives the app a login.
7. Open `https://<app-name>.azurewebsites.net`.

Watch: cold starts take a minute or two on B1; uploads are capped by
`maxUploadSize` in `.streamlit/config.toml`; App Service recycles the
container, so session folders do not survive a restart, which is fine because
nothing is meant to persist.

---

## Option 4 — Streamlit Community Cloud

Quickest, least private. **Files uploaded here go to Streamlit's servers.**
Use it for demonstrations, not client data.

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. **New app** → repository `LouisLoli-wq/eqs-measurement-analyser`, branch
   `main`, main file path `app.py`.
3. **Advanced settings** → Python 3.11.
4. **Deploy**. First build takes a few minutes.
5. The app is public by default. Under **Settings → Sharing**, restrict it to
   named viewers.

Community Cloud sleeps after inactivity and has about 1 GB of RAM, which is
enough for the files seen so far but not for a very long measurement period.

---

## Before any deployment

- [ ] `pytest` passes
- [ ] `git status` is clean, with no CSV, PNG, XLSX, PDF or notebook staged
- [ ] `.gitignore` is present and covers customer data
- [ ] No credential, token or local path anywhere in the repository
- [ ] `MAX_UPLOAD_MB` in `src/config.py` matches `maxUploadSize` in
      `.streamlit/config.toml`
- [ ] Whoever will use it has read the preliminary-sizing warning

## Updating a deployed app

```bash
git add -A && git commit -m "…" && git push
```

Options 3 and 4 redeploy on push. Options 1 and 2 need a `git pull` and a
restart.

---

## A note on running it in the browser

Pyodide and PyScript were assessed. pandas, numpy and matplotlib all run under
Pyodide, but Streamlit needs a server, so the browser-only route would mean
`stlite` plus a rewrite of the download layer and seaborn's heatmaps running in
WebAssembly, with a first load around 50 MB. It buys nothing over option 2,
where the data also never leaves the building. Not recommended, and not built.
