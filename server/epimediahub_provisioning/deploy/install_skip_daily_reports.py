"""Add the report module to the EXISTING Hetzner installation, without replacing
the analysis engine, customer configuration, queue, marker data or server units.
The generated shell installer embeds this module and all new files with hashes.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

APP_SERVICE = 'epimediahub-provisioning.service'
REPORT_SERVICE = 'epimediahub-episcene-report.service'
REPORT_TIMER = 'epimediahub-episcene-report.timer'
HOOK = '\nfrom skip_daily_reports import install as install_skip_daily_reports\ninstall_skip_daily_reports(app, db)\n'
INCLUDE = '{% if episcene_reports_enabled|default(false) %}{% include "skip_daily_report_launcher.html" %}{% endif %}\n'
FILES = ('skip_daily_reports.py','skip_report_telemetry.py','skip_daily_report_worker.py',
         'templates/skip_daily_report.html','templates/skip_daily_report_launcher.html','static/skip_daily_reports.js')


def command(args, **kwargs):
    return subprocess.run(args,check=True,text=True,capture_output=True,**kwargs).stdout.strip()


def property_of(name):
    return command(['systemctl','show',APP_SERVICE,'--property='+name,'--value'])


def active(unit):
    return subprocess.run(['systemctl','is-active','--quiet',unit],capture_output=True).returncode==0


def q(value):
    """systemd quoted path/value, with literal specifier and escape handling."""
    return '"' + str(value).replace('\\','\\\\').replace('"','\\"').replace('%','%%') + '"'


def prepare(base, files):
    if set(files) != set(FILES):
        raise RuntimeError('Unvollständiges Berichtspaket')
    prepared = {}
    for name,entry in files.items():
        raw = entry['content'].encode()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise RuntimeError('Prüfsumme fehlerhaft: '+name)
        prepared[name] = raw
    entry = (base/'wsgi.py').read_text()
    if 'install_skip_markers(app, db)' not in entry:
        raise RuntimeError('Unbekannter Dashboard-Einstieg; keine Dateien geändert')
    if 'install_skip_daily_reports(app, db)' not in entry:
        entry = entry.rstrip()+'\n'+HOOK
    prepared['wsgi.py'] = entry.encode()
    template = (base/'templates/skip_markers.html').read_text()
    if 'skip_daily_report_launcher.html' not in template:
        anchor = '{% include "skip_schedule.html" %}'
        if template.count(anchor)!=1:
            raise RuntimeError('Unbekannte Serienansicht; keine Dateien geändert')
        template = template.replace(anchor, INCLUDE+anchor)
    prepared['templates/skip_markers.html'] = template.encode()
    return prepared


def read_data_dir(env_file, environment):
    data = '/var/lib/epimediahub'
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            key,sep,value=line.partition('=')
            if sep and key.strip()=='EPIMEDIAHUB_DATA_DIR':
                parts=shlex.split(value,comments=True)
                if len(parts)!=1:raise RuntimeError('Ungültiges Datenverzeichnis')
                data=parts[0]
    for setting in shlex.split(environment):
        if setting.startswith('EPIMEDIAHUB_DATA_DIR='):
            data=setting.split('=',1)[1]
    if not Path(data).is_absolute():raise RuntimeError('Datenverzeichnis muss absolut sein')
    return Path(data)


def unit_files(base, data, user, group):
    group_line = 'Group='+group+'\n' if group else ''
    service = f'''[Unit]
Description=EpiScene daily analysis report
After={APP_SERVICE}
[Service]
Type=oneshot
User={user}
{group_line}WorkingDirectory={q(base)}
Environment={q('EPIMEDIAHUB_DATA_DIR='+str(data))}
ExecStart={q(base/'.venv/bin/python')} {q(base/'skip_daily_report_worker.py')}
Nice=10
TimeoutStartSec=900
MemoryMax=768M
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
UMask=0077
'''
    timer = f'''[Unit]
Description=EpiScene reports every morning at 07:00 Europe/Berlin
[Timer]
OnCalendar=*-*-* 07:00:00 Europe/Berlin
OnBootSec=2min
OnUnitInactiveSec=15min
Persistent=true
AccuracySec=1s
RandomizedDelaySec=0
Unit={REPORT_SERVICE}
[Install]
WantedBy=timers.target
'''
    return {REPORT_SERVICE:service.encode(),REPORT_TIMER:timer.encode()}


def atomic_write(path, content):
    path.parent.mkdir(parents=True,exist_ok=True)
    old=path.stat() if path.exists() else None
    fd,temp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(content)
        os.chmod(temp,old.st_mode & 0o777 if old else 0o644)
        if old:os.chown(temp,old.st_uid,old.st_gid)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def main(files):
    if os.geteuid()!=0:raise SystemExit('Bitte diesen Installer mit sudo ausführen.')
    base=Path(os.environ.get('EPIMEDIAHUB_APP_DIR','/opt/epimediahub/provisioning')).resolve()
    if not (base/'wsgi.py').is_file():raise SystemExit('Hetzner-Dashboard unter '+str(base)+' nicht gefunden.')
    if not (base/'skip_analysis_playlists.py').is_file():
        raise SystemExit('Dieses Update erwartet den zuletzt eingerichteten Stand mit eigenen Analyse-Playlists.')
    if Path(property_of('WorkingDirectory')).resolve()!=base or 'wsgi:app' not in property_of('ExecStart'):
        raise SystemExit('Dashboard-Dienst verwendet einen anderen Einstieg; Installation unverändert.')
    if not active(APP_SERVICE):raise SystemExit('Bitte zuerst den bestehenden Dashboard-Dienst starten.')
    user=property_of('User') or 'root';group=property_of('Group')
    env_file=Path(os.environ.get('EPIMEDIAHUB_ENV_FILE','/etc/epimediahub/provisioning.env'))
    data=read_data_dir(env_file,property_of('Environment'))
    if not (data/'provisioning.db').is_file():raise SystemExit('Bestehende Datenbank nicht gefunden; keine neue angelegt.')
    prepared=prepare(base,files)
    python=base/'.venv/bin/python'
    units=Path('/etc/systemd/system')
    if (units/(REPORT_SERVICE+'.d')).exists() or (units/(REPORT_TIMER+'.d')).exists():
        raise SystemExit('Berichtsdienst hat zusätzliche lokale Einstellungen; bitte vor dem Update prüfen.')
    unit_data=unit_files(base,data,user,group)
    command(['systemd-analyze','calendar','*-*-* 07:00:00 Europe/Berlin'])
    with tempfile.TemporaryDirectory(prefix='episcene-report-') as temporary:
        stage=Path(temporary)
        for name,raw in prepared.items():
            path=stage/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        command([str(python),'-c',
            "import ast,pathlib,sys; from jinja2 import Environment; p=pathlib.Path(sys.argv[1]); "
            "[ast.parse(f.read_text()) for f in p.glob('*.py')]; "
            "[Environment().parse(f.read_text()) for f in (p/'templates').glob('*.html')]",str(stage)])
    (base/'backups').mkdir(mode=0o700,parents=True,exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix='daily-reports-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-',dir=base/'backups'))
    targets={base/name:raw for name,raw in prepared.items()}
    targets.update({units/name:raw for name,raw in unit_data.items()})
    originals={}
    for index,path in enumerate(targets):
        saved=backup/(str(index)+'-'+path.name)
        if path.exists():shutil.copy2(path,saved);originals[path]=saved
        else:originals[path]=None
    receipt={'created_at':datetime.now(timezone.utc).isoformat(),'database':str(data/'provisioning.db'),
             'files':{str(path):str(saved) if saved else None for path,saved in originals.items()}}
    (backup/'files.json').write_text(json.dumps(receipt,indent=2))
    timer_active=active(REPORT_TIMER)
    timer_enabled=subprocess.run(['systemctl','is-enabled','--quiet',REPORT_TIMER],capture_output=True).returncode==0
    prefix=['runuser','-u',user,'--'] if user!='root' else []
    runner=prefix+['env','PYTHONPATH='+str(base),'EPIMEDIAHUB_DATA_DIR='+str(data),str(python)]
    changed=[]
    try:
        # This is additive: analysis keeps running, with its current versions.
        for path,raw in targets.items():
            atomic_write(path,raw);changed.append(path)
        command(runner+['-c',
            "from pathlib import Path; import os; from skip_database import connect; "
            "from skip_daily_reports import migrate,register_build; "
            "con=connect(Path(os.environ['EPIMEDIAHUB_DATA_DIR'])/'provisioning.db'); "
            "migrate(con); register_build(con); con.commit(); con.close()"],cwd=base)
        command(['systemctl','daemon-reload'])
        command(['systemctl','restart',APP_SERVICE])
        # Verify authenticated and anonymous routes through the local Flask app,
        # with only the established data directory (no provider requests).
        check="""from wsgi import app
app.config['TESTING']=True
c=app.test_client()
assert c.get('/admin/skip/reports').status_code==302
with c.session_transaction() as s:s['admin']=True
assert c.get('/admin/skip/reports/latest').status_code==200
assert c.get('/admin/skip/reports').status_code==200
r=c.get('/admin/skip')
assert r.status_code==200 and b'episcene-report-dialog' in r.data
"""
        command(runner+['-c',check],cwd=base)
        if not active(APP_SERVICE):raise RuntimeError('Dashboard-Dienst ist nicht aktiv')
        command(['systemctl','enable',REPORT_TIMER])
        command(['systemctl','restart',REPORT_TIMER])
        command(['systemctl','start',REPORT_SERVICE])
        if not active(REPORT_TIMER):raise RuntimeError('Berichts-Timer ist nicht aktiv')
        command(runner+['-c',
            "import os; from pathlib import Path; from skip_database import connect; "
            "from skip_daily_reports import due_day,read_report; "
            "con=connect(Path(os.environ['EPIMEDIAHUB_DATA_DIR'])/'provisioning.db'); "
            "r=read_report(con); assert r and r['day']==due_day().isoformat(); con.close()"],cwd=base)
    except BaseException:
        subprocess.run(['systemctl','stop',REPORT_TIMER,REPORT_SERVICE],capture_output=True)
        if not timer_enabled:subprocess.run(['systemctl','disable',REPORT_TIMER],capture_output=True)
        for path in reversed(changed):
            saved=originals[path]
            if saved:shutil.copy2(saved,path)
            else:path.unlink(missing_ok=True)
        subprocess.run(['systemctl','daemon-reload'],capture_output=True)
        if timer_active:subprocess.run(['systemctl','start',REPORT_TIMER],capture_output=True)
        subprocess.run(['systemctl','restart',APP_SERVICE],capture_output=True)
        print('Update zurückgenommen. Analyse- und Kundendaten wurden nicht zurückgesetzt. Sicherung: '+str(backup),flush=True)
        raise
    print('Fertig: EpiScene-Tagesbericht täglich um 07:00 Uhr (Europe/Berlin).',flush=True)
    print('Serien-Dashboard neu laden: Der aktuelle Bericht öffnet sich einmal täglich automatisch.',flush=True)
    print('Detaillierte Messungen beginnen mit der Installation; der erste Bericht ist als unvollständig markiert.',flush=True)
    print('Sicherung der geänderten Dateien: '+str(backup),flush=True)

