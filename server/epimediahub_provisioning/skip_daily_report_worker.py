"""Run by systemd at 07:00 Berlin; startup and retry runs fill missing days."""
import fcntl
import os
from pathlib import Path


def main():
    folder = Path(os.environ.get('EPIMEDIAHUB_DATA_DIR','/var/lib/epimediahub'))
    # Never import wsgi or app here: their unrelated migrations could change the
    # queue. The installer creates the report schema in the existing database.
    from skip_database import connect
    from skip_daily_reports import generate_due
    with (folder/'episcene-reports.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return
        written = generate_due(lambda: connect(folder/'provisioning.db'))
        print('EpiScene Tagesberichte: ' + (', '.join(written) if written else 'aktuell'),flush=True)


if __name__ == '__main__':
    main()
