#!/usr/bin/env python3
"""Read-only EpiScene source exporter. No service, queue or database changes."""
import argparse, datetime, json, os, re, sys, tempfile, zipfile
from pathlib import Path

EXTENSIONS={'.py','.pyi','.sh','.js','.jsx','.ts','.tsx','.go'}
OMIT_DIRS={'.git','.hg','.svn','.venv','venv','env','__pycache__',
 'node_modules','site-packages','dist','build','target','.gradle','.next',
 '.cache','logs','log','data','storage','uploads','downloads','backups','backup',
 'secrets','credentials','certs','keys','private','media','recordings',
 'cache','tmp','temp','sessions','customer_data'}
OMIT_FILE=re.compile(r'(?i)(credential|secret|password|passwd|private[_-]?key|\.env|token[_-]?dump|api[_-]?keys|customer[_-]?data|database[_-]?dump)')
LITERAL=re.compile(
 r'(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|'
 r'auth[_-]?token|bearer[_-]?token|password|passwd|secret|private[_-]?key|'
 r'authorization|webhook[_-]?secret|database[_-]?url|db[_-]?password)\b'
 r'\s*[=:]\s*)([\'\"])([^\r\n\'\"]{2,})(\2)')
MASK=[
 re.compile(r'(?:ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9]{20,}'),
 re.compile(r'github_pat_[A-Za-z0-9_]{20,}'),
 re.compile(r'sk-[A-Za-z0-9_-]{20,}'),
 re.compile(r'AKIA[0-9A-Z]{16}'),
 re.compile(r'(?i)(?<=://)[^\s/:@]+:[^\s/@]+@'),
 re.compile(r'eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'),
 re.compile(r'(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])')]
KEYBLOCK=re.compile(r'-----BEGIN (?:[A-Z ]* )?PRIVATE KEY-----|-----BEGIN OPENSSH PRIVATE KEY-----')
MAX_FILE=3000000
MAX_TOTAL=30000000
MAX_FILES=1500

def sanitize(data):
 text=data.decode('utf-8','replace')
 if KEYBLOCK.search(text): return None,0
 redactions=0
 def mask_literal(m):
  nonlocal redactions
  redactions+=1
  return m.group(1)+m.group(2)+'REDACTED_FOR_EXPORT'+m.group(4)
 text=LITERAL.sub(mask_literal,text)
 for rx in MASK:
  text,n=rx.subn('REDACTED_FOR_EXPORT',text)
  redactions+=n
 return text.encode('utf-8'),redactions

def main():
 p=argparse.ArgumentParser(description='Read-only source code export')
 p.add_argument('--analysis',type=Path,default=Path('/opt/epimediahub/analysis'))
 p.add_argument('--provisioning',type=Path,default=Path('/opt/epimediahub/provisioning'))
 p.add_argument('--output',type=Path,default=Path('/root/episcene-backend-source.zip'))
 a=p.parse_args()
 if a.output.is_symlink() or not a.output.parent.is_dir():
  raise RuntimeError('INVALID_OUTPUT_DESTINATION')
 roots=[('analysis',a.analysis),('provisioning',a.provisioning)]
 bundle=[]
 skipped={'too_large_or_binary':0,'contains_private_key':0}
 total=0
 for label,base in roots:
  if not base.is_dir() or base.is_symlink():
   raise RuntimeError('SOURCE_DIRECTORY_MISSING: '+label)
  for directory,dirs,files in os.walk(base,followlinks=False):
   dirs[:]=sorted(d for d in dirs if d.lower() not in OMIT_DIRS
                  and not d.startswith('.') and
                  not (Path(directory)/d).is_symlink())
   for filename in sorted(files):
    path=Path(directory)/filename
    if (path.is_symlink() or filename.startswith('.') or
        path.suffix.lower() not in EXTENSIONS or OMIT_FILE.search(filename)
        or filename.endswith('.min.js')):continue
    if not path.is_file() or path.stat().st_size>MAX_FILE:
     skipped['too_large_or_binary']+=1
     continue
    data=path.read_bytes()
    if b'\0' in data:
     skipped['too_large_or_binary']+=1
     continue
    clean,n=sanitize(data)
    if clean is None:
     skipped['contains_private_key']+=1
     continue
    total+=len(clean)
    if total>MAX_TOTAL or len(bundle)>=MAX_FILES:
     raise RuntimeError('EXPORT_TOO_LARGE')
    bundle.append((label+'/'+path.relative_to(base).as_posix(),clean,n))
 if not bundle:raise RuntimeError('NO_SOURCE_FOUND')
 info={'collected_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'file_count':len(bundle),'redacted_literals':sum(x[2] for x in bundle),
       'skipped':skipped,
       'warning':'Review archive before uploading; masking is best-effort'}
 tmp=None
 try:
  with tempfile.NamedTemporaryFile(dir=a.output.parent,prefix='.episcene-',suffix='.zip',delete=False) as f:
   tmp=Path(f.name)
  with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
   for name,clean,n in bundle:z.writestr(name,clean)
   z.writestr('EXPORT_INFO.json',json.dumps(info,indent=2))
  os.chmod(tmp,0o600)
  os.replace(tmp,a.output)
 finally:
  if tmp and tmp.exists():tmp.unlink()
 print('ARCHIVE_READY:',a.output)
 print('SOURCE_FILES:',len(bundle),'MASKED_VALUES:',info['redacted_literals'])
 print('UPLOAD_ZIP_HERE_AFTER_REVIEW')

if __name__=='__main__':
 try:main()
 except (OSError,RuntimeError,ValueError) as e:
  print('EXPORT_BLOCKED:',e,file=sys.stderr)
  sys.exit(2)
