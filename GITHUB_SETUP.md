# Simple Mac Terminal upload — Akili RC4

**GitHub username:** `irenee28`  
**Name:** Irénée Akilimali  
**Commercial contact:** shukranimungu@gmail.com

Download these files into your Mac **Downloads** folder:

- `akili-runtime-v0.1.0-rc4-irenee28.zip`
- `akili-commercial-private-rc4-irenee28.zip`

## 1. Create the GitHub repositories

On GitHub, create:

1. `akili-runtime` — **Public**
2. `akili-commercial-private` — **Private**

Do not add a README, license, or `.gitignore` on GitHub.

## 2. Upload the public repository

```bash
cd ~/Downloads
rm -rf akili-runtime
unzip akili-runtime-v0.1.0-rc4-irenee28.zip
cd akili-runtime

git init
git branch -M main
git config user.name "Irénée Akilimali"
git config user.email "shukranimungu@gmail.com"

git add .
git commit -m "Initial public Akili Runtime release"

git remote add origin https://github.com/irenee28/akili-runtime.git
git push -u origin main
```

Public URL:

```text
https://github.com/irenee28/akili-runtime
```

## 3. Upload the private repository

```bash
cd ~/Downloads
rm -rf akili-commercial-private
unzip akili-commercial-private-rc4-irenee28.zip
cd akili-commercial-private

git init
git branch -M main
git config user.name "Irénée Akilimali"
git config user.email "shukranimungu@gmail.com"

git add .
git commit -m "Initial private Akili commercial repository"

git remote add origin https://github.com/irenee28/akili-commercial-private.git
git push -u origin main
```

Private URL:

```text
https://github.com/irenee28/akili-commercial-private
```

Confirm on GitHub that `akili-commercial-private` is marked **Private**.

## 4. Verify

```bash
git remote -v
git status
```

Expected:

```text
On branch main
nothing to commit, working tree clean
```

Do not create the final `v0.1.0` tag yet.
