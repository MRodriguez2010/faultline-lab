"""Own one loopback-only PostgreSQL container and volume. Never discovers other apps."""
import argparse
import json
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".runtime" / "database.json"
IMAGE = "postgres@sha256:051f7b7b3abdd564d5d1bd1e8c4b9c1b6e77087d1dd22020ede611c096a272e0"


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, timeout=120).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "status"])
    args = parser.parse_args()
    if args.action == "start":
        if STATE.exists():
            print("Existing lab state; use status or stop before starting a fresh lab.")
            return
        STATE.parent.mkdir(parents=True, exist_ok=True)
        owner = uuid.uuid4().hex
        volume = f"faultline-{owner}"
        docker("volume", "create", "--label", f"faultline.owner={owner}", volume)
        container = None
        try:
            container = docker("run", "-d", "--name", volume, "--label", f"faultline.owner={owner}",
              "--memory", "512m", "--cpus", "2", "--pids-limit", "128",
              "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "-e", "POSTGRES_DB=faultline",
              "-p", "127.0.0.1::5432", "-v", f"{volume}:/var/lib/postgresql/data", IMAGE)
            port = json.loads(docker("inspect", container))[0]["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"]
            state = {"container": container, "volume": volume, "owner": owner, "image": IMAGE,
                     "dsn": f"host=127.0.0.1 port={port} dbname=faultline user=postgres"}
            STATE.write_text(json.dumps(state, indent=2)+"\n")
            STATE.chmod(0o600)
            for _ in range(40):
                # The image's initialization server accepts only Unix sockets.
                # Wait for the final TCP listener, not that temporary server.
                check = subprocess.run(["docker", "exec", container, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", "-d", "faultline"], capture_output=True)
                if check.returncode == 0:
                    print(json.dumps({"status": "ready", "port": int(port)}))
                    return
                time.sleep(.25)
            raise RuntimeError("PostgreSQL readiness timeout; inspect this lab container")
        except Exception:
            if container:
                subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            subprocess.run(["docker", "volume", "rm", volume], capture_output=True)
            STATE.unlink(missing_ok=True)
            raise
    elif not STATE.exists():
        print("No lab database is running.")
    else:
        state = json.loads(STATE.read_text())
        info = json.loads(docker("inspect", state["container"]))[0]
        if info["Config"]["Labels"].get("faultline.owner") != state["owner"]:
            raise RuntimeError("ownership mismatch")
        if args.action == "status":
            print(json.dumps({"running": info["State"]["Running"], "image": state["image"]}))
        else:
            vinfo = json.loads(docker("volume", "inspect", state["volume"]))[0]
            if vinfo["Labels"].get("faultline.owner") != state["owner"]:
                raise RuntimeError("volume ownership mismatch")
            docker("rm", "-f", state["container"])
            docker("volume", "rm", state["volume"])
            STATE.unlink()
            print("Stopped and removed only this lab's container and disposable data volume.")


if __name__ == "__main__":
    main()
