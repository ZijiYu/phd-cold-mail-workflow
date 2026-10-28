"""Run the outreach dashboard.

    python -m dashboard --data outreach
    python -m dashboard --data outreach --open
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m dashboard", description="PhD outreach dashboard + REST API")
    ap.add_argument("--data", default="outreach", help="folder containing campaign folders (default: ./outreach)")
    ap.add_argument("--state-dir", default=str(Path.home() / ".phd-outreach-dashboard"),
                    help="where the API token, Google client and Gmail token live (default: ~/.phd-outreach-dashboard)")
    ap.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1; keep it local)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="open the dashboard in a browser")
    args = ap.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("Missing dependencies. Run: pip install -r dashboard/requirements.txt", file=sys.stderr)
        return 1
    from .app.api import create_app

    data = Path(args.data)
    if not data.is_dir():
        data.mkdir(parents=True)
        print(f"Created empty data folder: {data.resolve()} (add a campaign from the dashboard)")
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print(f"WARNING: binding to {args.host} exposes the dashboard beyond this computer.", file=sys.stderr)

    app = create_app(data, Path(args.state_dir))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Dashboard:  {url}")
    print(f"API docs:   {url}api/docs")
    print(f"API token:  {Path(args.state_dir) / 'api_token'}")
    if args.open:
        webbrowser.open(url)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
