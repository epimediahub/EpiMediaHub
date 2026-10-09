#!/usr/bin/env python3
"""Install the Finland node agent; the dashboard token is entered privately."""
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vpn_finland_agent import Agent, atomic

UNIT = """[Unit]
Description=EpiMediaHub Finland VPN license agent
After=network-online.target wg-quick@wg0.service
Wants=network-online.target
Requires=wg-quick@wg0.service
PartOf=wg-quick@wg0.service

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /opt/epimediahub-vpn/vpn_finland_agent.py
ExecStopPost=/usr/bin/python3 /opt/epimediahub-vpn/vpn_finland_agent.py --close
Restart=always
RestartSec=5
TimeoutStopSec=15
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
PrivateTmp=true
ReadWritePaths=/etc/wireguard /var/lib/epimediahub-vpn
CapabilityBoundingSet=CAP_NET_ADMIN CAP_DAC_OVERRIDE
UMask=0077

[Install]
WantedBy=multi-user.target
"""



def read_dashboard_url():
    """Read the optional dashboard URL from a terminal without seeking on a TTY.

    A POSIX terminal is not seekable. Opening /dev/tty in update mode ("r+")
    makes Python's text wrapper attempt an illegal seek on some environments.
    Never read the dashboard VPN token here; getpass handles that separately.
    """
    fallback = "https://api.epimediahub.com"
    try:
        with open("/dev/tty", "r", encoding="utf-8") as terminal:
            print(f"Dashboard-URL [{fallback}]: ", file=sys.stderr, end="", flush=True)
            value = terminal.readline()
    except (OSError, UnicodeError) as exc:
        raise SystemExit(
            "Keine interaktive Konsole verfuegbar. Installer direkt im "
            "SSH-Terminal ausfuehren (nicht mit curl | bash)."
        ) from exc
    if value == "":
        raise SystemExit("Dashboard-URL-Eingabe abgebrochen; nichts installiert.")
    return value.strip() or fallback

def main():
    if os.geteuid()!=0:raise SystemExit("Bitte als root auf dem Finnland-VPN-Server starten.")
    wg=Path("/etc/wireguard/wg0.conf")
    if not wg.is_file() or not shutil.which("wg"):raise SystemExit("WireGuard wg0 muss bereits eingerichtet sein.")
    destination=Path("/opt/epimediahub-vpn")
    config_path=Path("/etc/epimediahub-vpn-agent.json")
    source=Path(__file__).resolve().parents[1]/"vpn_finland_agent.py"
    if config_path.exists():
        config=json.loads(config_path.read_text())
    else:
        print("Kopplung mit dem Dashboard. Das Token nicht in Chats oder GitHub einfügen.")
        url = read_dashboard_url()
        token=getpass.getpass("VPN-Kopplungstoken vom Dashboard-Server: ")
        config={"dashboard_url":url,"token":token,"interface":"wg0"}
    agent=Agent(config)
    from vpn_finland_agent import validate
    try:validate(agent.request("/v1/vpn-agent/desired"),agent.subnet)
    except Exception as error:raise SystemExit(f"Dashboard-Kopplung fehlgeschlagen ({type(error).__name__}). Nichts installiert.") from None
    print("Dashboard authentifiziert. Agent verwaltet nur dort ausdrücklich zugeordnete Geräte.")
    destination.mkdir(parents=True,exist_ok=True)
    Path("/var/lib/epimediahub-vpn").mkdir(mode=0o700,exist_ok=True)
    unit_path=Path("/etc/systemd/system/epimediahub-vpn-agent.service")
    with tempfile.TemporaryDirectory(prefix="epi-vpn-agent-backup-") as directory:
        backup=Path(directory)
        targets=[destination/"vpn_finland_agent.py",config_path,unit_path]
        for index,path in enumerate(targets):
            if path.exists():shutil.copy2(path,backup/str(index))
        was_active=subprocess.run(["systemctl","is-active","--quiet","epimediahub-vpn-agent.service"]).returncode==0
        try:
            if was_active:subprocess.run(["systemctl","stop","epimediahub-vpn-agent.service"],check=True)
            shutil.copy2(source,targets[0]);targets[0].chmod(0o644)
            atomic(config_path,json.dumps(config))
            unit_path.write_text(UNIT);unit_path.chmod(0o644)
            subprocess.run(["systemctl","daemon-reload"],check=True)
            subprocess.run(["systemctl","enable","--now","epimediahub-vpn-agent.service"],check=True)
            subprocess.run(["systemctl","is-active","--quiet","epimediahub-vpn-agent.service"],check=True)
        except Exception:
            subprocess.run(["systemctl","stop","epimediahub-vpn-agent.service"],check=False)
            for index,path in enumerate(targets):
                saved=backup/str(index)
                if saved.exists():shutil.copy2(saved,path)
                else:path.unlink(missing_ok=True)
            subprocess.run(["systemctl","daemon-reload"],check=False)
            if was_active:subprocess.run(["systemctl","start","epimediahub-vpn-agent.service"],check=False)
            raise
    print("VPN-Agent installiert. Im Dashboard auf die aktuelle Serverbestätigung achten.")


if __name__=="__main__":main()
