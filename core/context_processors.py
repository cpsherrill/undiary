import os


def version(request):
    """Cloud Run stamps K_REVISION; dev says dev. Shown in the account
    menu so a stale client can be diagnosed by looking at it."""
    return {"app_revision": os.environ.get("K_REVISION", "dev")}
