# Kerala Cooking Flask App — Oracle Cloud Deployment Guide

## Server Details
| Item | Value |
|---|---|
| **Provider** | Oracle Cloud Free Tier |
| **Public IP** | 140.245.223.79 |
| **Shape** | VM.Standard.E2.1.Micro (1 OCPU, 1GB RAM) |
| **OS** | Ubuntu 20.04 |
| **Region** | AP-Hyderabad-1 |
| **App directory** | `/home/ubuntu/cooking-app` |
| **GitHub repo** | https://github.com/vikasjyani/kerala-flask-app |
| **SSH key file** | `oracle_flask.key` (save this securely) |

---

## What We Set Up (Summary)

1. Created Oracle Cloud VM instance (E2.1.Micro, Ubuntu 20.04)
2. Assigned ephemeral public IP to the VM
3. Opened ports 80 and 443 in Oracle Security List
4. Fixed Ubuntu iptables firewall rules
5. Installed Python 3.9, pip, venv, nginx, git on the VM
6. Cloned Flask app from GitHub to `/home/ubuntu/cooking-app`
7. Created Python virtual environment with all dependencies
8. Created `.env` file with production settings
9. Created Gunicorn systemd service (`cooking-flask.service`)
10. Configured Nginx as reverse proxy
11. App is live at http://140.245.223.79

---

## SSH Into the Server

```bash
# From Windows PowerShell (navigate to key location first)
cd C:\Users\Admin\Downloads
ssh -i oracle_flask.key ubuntu@140.245.223.79
```

If permission error on the key:
```powershell
icacls oracle_flask.key /inheritance:r /grant:r "$($env:USERNAME):(R)"
```

---

## Updating the App When Code Changes

**The app does NOT auto-update.** When you push code to GitHub, you must manually SSH in and pull the changes. Here is the full update process:

### Step 1 — Push from your local machine (Windows)
```bash
# In your project folder
git add .
git commit -m "kseb logo added"
git push origin main
```

### Step 2 — SSH into the server
```bash
ssh -i oracle_flask.key ubuntu@140.245.223.79
```

### Step 3 — Pull latest code
```bash
cd /home/ubuntu/cooking-app
git pull https://ghp_YOUR_TOKEN@github.com/vikasjyani/kerala-flask-app.git main
```

### Step 4 — Restart the app
```bash
sudo systemctl restart cooking-flask
sudo systemctl status cooking-flask
```

That's it. Nginx does not need to be restarted unless you change the nginx config.

---

### Quick One-Liner Update (after SSH)
```bash
cd /home/ubuntu/cooking-app && git pull https://ghp_YOUR_TOKEN@github.com/vikasjyani/kerala-flask-app.git main && sudo systemctl restart cooking-flask
```

---

### If requirements.txt changed (new packages added)
```bash
cd /home/ubuntu/cooking-app
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart cooking-flask
```

---

## Downloading Database Files

The app has two SQLite databases on the server:

| File | Contains |
|---|---|
| `cooking_webapp.db` | Master reference data (constants, fuel costs, emission factors) |
| `user_data.db` | User submissions and form data |

### Download to your Windows PC (run in PowerShell)

```powershell
# Download user_data.db (user submissions)
scp -i oracle_flask.key ubuntu@140.245.223.79:/home/ubuntu/cooking-app/user_data.db C:\Users\Admin\Desktop\user_data_backup.db

# Download cooking_webapp.db (reference data)
scp -i oracle_flask.key ubuntu@140.245.223.79:/home/ubuntu/cooking-app/cooking_webapp.db C:\Users\Admin\Desktop\cooking_webapp_backup.db
```

### Upload updated DB back to server (if you edit locally)
```powershell
scp -i oracle_flask.key C:\Users\Admin\Desktop\cooking_webapp.db ubuntu@140.245.223.79:/home/ubuntu/cooking-app/cooking_webapp.db
```

After uploading, restart the app:
```bash
sudo systemctl restart cooking-flask
```

### View DB contents on server
```bash
# Install sqlite3 if not available
sudo apt install -y sqlite3

# Open user_data.db
sqlite3 /home/ubuntu/cooking-app/user_data.db

# Inside sqlite3 shell:
.tables                    # list all tables
SELECT * FROM feedback;    # example query
.quit                      # exit
```

### Auto Daily Backup (optional but recommended)
```bash
# On the server, set up a cron job
crontab -e

# Add this line (backs up every day at 2am):
0 2 * * * cp /home/ubuntu/cooking-app/user_data.db /home/ubuntu/user_data_$(date +\%Y\%m\%d).db
```

---

## Connecting a Custom Domain
SESSION_COOKIE_SECURE=false
### Step 1 — Point DNS to Oracle IP

Log into your domain registrar (GoDaddy / Namecheap / Hostinger etc.) and add these DNS records:

| Type | Name | Value | TTL |
|---|---|---|---|
| A | `@` | `140.245.223.79` | 3600 |
| A | `www` | `140.245.223.79` | 3600 |

Wait **10–30 minutes** for DNS to propagate. Test with:
```bash
ping yourdomain.com
# Should resolve to 140.245.223.79
```

### Step 2 — Update Nginx Config with Domain

```bash
sudo nano /etc/nginx/sites-available/cooking-flask
```

Change this line:
```nginx
server_name _;
```
To:
```nginx
server_name yourdomain.com www.yourdomain.com;
```

Save (Ctrl+X → Y → Enter) and reload:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

Test: `http://yourdomain.com` should load the app.

### Step 3 — Install Free SSL Certificate (HTTPS)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Follow the prompts:
- Enter your email
- Agree to terms → `A`
- Redirect HTTP to HTTPS → `2`

Certbot automatically:
- Gets a free Let's Encrypt certificate
- Updates nginx config for HTTPS
- Sets up auto-renewal every 90 days

Test: `https://yourdomain.com` should load with padlock.

### Verify Auto-Renewal Works
```bash
sudo certbot renew --dry-run
```

---

## Useful Server Commands

```bash
# Check app status
sudo systemctl status cooking-flask

# Restart app
sudo systemctl restart cooking-flask

# View live app logs
tail -f /home/ubuntu/cooking-app/error.log

# View access logs
tail -f /home/ubuntu/cooking-app/access.log

# View nginx error logs
sudo tail -f /var/log/nginx/error.log

# Check what's using port 80
sudo ss -tlnp | grep :80

# Reboot server
sudo reboot
```

---

## Important Files on Server

```
/home/ubuntu/cooking-app/
├── app.py                  ← Flask app entry point
├── cooking_webapp.db       ← Master reference database
├── user_data.db            ← User submissions database
├── .env                    ← Environment variables (NOT in git)
├── venv/                   ← Python virtual environment
├── access.log              ← HTTP access log
└── error.log               ← Gunicorn error log

/etc/nginx/sites-available/cooking-flask   ← Nginx config
/etc/systemd/system/cooking-flask.service  ← Systemd service
```

---

## .env File on Server

Location: `/home/ubuntu/cooking-app/.env`

```env
FLASK_ENV=production
SECRET_KEY=Kerala2024#Cooking$Tool@Secure!XyZ9
DATABASE_PATH=/home/ubuntu/cooking-app/cooking_webapp.db
```

To edit:
```bash
nano /home/ubuntu/cooking-app/.env
sudo systemctl restart cooking-flask
```

---

## If the VM Reboots

Everything auto-starts because we ran `systemctl enable`:
- `cooking-flask` service starts automatically
- `nginx` starts automatically

No manual intervention needed after a reboot.





