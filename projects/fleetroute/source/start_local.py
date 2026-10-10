from __future__ import annotations

import os
import secrets

import uvicorn

if __name__ == "__main__":
    os.environ.setdefault("VRP_APP_TOKEN", secrets.token_urlsafe(12))
    token = os.environ["VRP_APP_TOKEN"]
    port = int(os.getenv("PORT", "8080"))
    print(f"FleetRoute Control: http://127.0.0.1:{port}/?token={token}")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
