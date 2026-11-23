# Run Grace Furnitures Invoice in GitHub Codespaces

## Start

1. Open this repository on GitHub.
2. Click **Code** → **Codespaces** → **Create codespace on main**.
3. Wait for the Codespace to finish setup. Dependencies install automatically.
4. In the terminal, run:

```bash
./start_codespaces.sh
```

5. GitHub will detect port **5050**. Open the forwarded port from the **Ports** tab or the popup notification.

Default first login:

- Username: `admin`
- Password: `Grace@2026`

Change the password after first login.

## iPad / iPhone

Open GitHub in Safari or Chrome, open the repository, create/start the Codespace, run `./start_codespaces.sh`, then open port 5050 from the Ports panel. The forwarded HTTPS URL works in the browser without your Mac being on.

## Port visibility

Keep port 5050 **Private** for invoice use. A private forwarded port requires your GitHub login. Do not make it Public unless you understand that anyone with the URL may be able to reach the login page.

## Data persistence warning

The SQLite database file is stored inside the Codespace. It normally remains while that Codespace exists, but Codespaces are development environments, not permanent business hosting. If the Codespace is deleted, its local database is deleted too.

Back up `grace_web.db` regularly by downloading it from the Codespace or committing/exporting a backup outside the repository. Do **not** commit the live invoice database to a public repository.

## Restart later

When a Codespace has stopped:

1. GitHub → repository → **Code** → **Codespaces**.
2. Start the existing Codespace.
3. Run `./start_codespaces.sh` again.
4. Open port 5050.
