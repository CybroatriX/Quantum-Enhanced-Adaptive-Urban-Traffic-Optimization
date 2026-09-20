"""Runner script for the Python optimization backend service."""

import os
from optimization.service import create_app

if __name__ == "__main__":
    import socket
    import sys
    port = int(os.environ.get("PYTHON_OPTIMIZER_PORT", os.environ.get("PORT", 5001)))
    host = os.environ.get("HOST", "127.0.0.1")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex((host, port)) == 0:
            print(f"\n[FlowQ Info] Port {port} is already in use.")
            print(f"FlowQ Python Optimizer backend is already actively running at http://{host}:{port}\n")
            sys.exit(0)
    app = create_app()
    print(f"FlowQ Canonical Python Optimizer running at http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
