#!/usr/bin/env python3
import sqlite3
p='file:/var/lib/epimediahub/provisioning.db?mode=ro'
db=sqlite3.connect(p,uri=True)
db.row_factory=sqlite3.Row
db.execute('PRAGMA query_only=ON')
sql="""SELECT r.id,COALESCE(a.title,r.title) title,COALESCE(a.season,r.season) s,COALESCE(a.episode,r.episode) e,a.playlist_id p,r.source src,r.status st,r.start_ms b,r.end_ms z,r.created_at at FROM skip_records r LEFT JOIN skip_assets a ON a.asset_key=r.asset_key WHERE lower(r.segment_type)='intro' AND (lower(COALESCE(a.title,r.title)) LIKE '%berlino%' OR lower(COALESCE(a.title,r.title)) LIKE '%bridgerton%' OR lower(r.title) LIKE '%berlino%' OR lower(r.title) LIKE '%bridgerton%')"""
rows=db.execute(sql).fetchall()
targets=[('berlino',1,2),('bridgerton',1,1),('bridgerton',1,2),('bridgerton',1,3),('bridgerton',2,1)]
manual={'device','manual','app','user'}
for name,s,e in targets:
    subset=[r for r in rows if name in str(r['title']).casefold() and (r['s'],r['e'])==(s,e)]
    subset.sort(key=lambda r:(str(r['at'] or ''),int(r['id'])))
    print(f'\n{name.upper()} S{s}E{e}: {len(subset)} Intro-Eintraege')
    n=0
    for r in subset:
        is_manual=str(r['src']).casefold() in manual
        if is_manual:n+=1
        ms=lambda x:'?' if x is None else f'{int(x)/1000:.2f}s'
        tag=f'MANUELL-{n}' if is_manual else 'automatisch'
        print(f"{tag} #{r['id']} P{r['p']} {r['src']}/{r['st']} {ms(r['b'])}-{ms(r['z'])} erstellt={r['at']}")
    if name=='berlino':print(f'Manuelle Intros: {n}; Nutzer bestaetigt das ZWEITE gesetzte Intro (nur bei genau zwei eindeutig)')
print('\nNUR LESEN: keine Markierungen veraendert')
db.close()
