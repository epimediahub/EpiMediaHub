import importlib.util, json, sqlite3, tempfile
from pathlib import Path

spec=importlib.util.spec_from_file_location('rec',str(Path(__file__).resolve().parent/'reconcile_feedback.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); dbfile=root/'db.sqlite3'
    with sqlite3.connect(dbfile) as db:
        db.execute('CREATE TABLE skip_assets (asset_key TEXT PRIMARY KEY, playlist_id INTEGER,title TEXT,season INTEGER,episode INTEGER)')
        db.execute('CREATE TABLE skip_records (id INTEGER PRIMARY KEY,asset_key TEXT,title TEXT,season INTEGER,episode INTEGER, segment_type TEXT,source TEXT,status TEXT,start_ms INTEGER,end_ms INTEGER,created_at TEXT)')
        for id,season,episode in [(2291,1,1),(2293,1,2),(2295,1,3)]:
            db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',(id,'missing-asset-'+str(id),'Bridgerton',season,episode,'intro','device','pending',0,20000,'2026-10-14T15:22:53.620464Z'))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',(2290,'missing-old','Bridgerton',1,1,'intro','device','pending',0,20000,'2026-10-14T12:22:53.620464Z'))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',(2292,'missing-wrong','Bridgerton',4,9,'intro','device','pending',0,20000,'2026-10-14T15:22:53.620464Z'))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',(2298,'linked','Bridgerton',1,2,'intro','device','pending',0,20000,'2026-10-14T15:22:53.620464Z'))
        db.execute("INSERT INTO skip_assets VALUES('linked',10,'Bridgerton',1,2)")
        db.commit()
        data=m.inspect(db,{'episodes':[{'id':f'REF-0{i}', 'series':'Bridgerton','season':1,'episode':i} for i in range(1,4)]},{'recorded_utc':'2026-10-14T13:18:29.630874+00:00'})
    assert len(data)==3, data
    assert {x['record_id'] for x in data}=={2291,2293,2295},data
    assert all(x['playlist_inferred'] is None for x in data)
print('PASS: read-only SQLite; three orphan references discovered; excludes pre-baseline, linked and unrelated')
