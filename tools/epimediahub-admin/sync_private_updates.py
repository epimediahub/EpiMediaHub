#!/usr/bin/env python3
"""Safely synchronize GitHub's PRIVATE Admin release artifact to Hetzner.

Token: owner-only admin-mobile/github-actions.token, fine-grained repository
Actions:read permission. No release APK on public GitHub Releases or player
updater. One attempt per timer tick; rollback is natural via immutable signed
APK and monotonic version, while Android verifies installed signing cert.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from publish_private_release import publish

API="https://api.github.com"
REPO="epimediahub/EpiMediaHub"
WORKFLOW="epimediahub-admin-private-release.yml"
ARTIFACT="epimediahub-admin-signed-private-server-bundle"
MAX_ZIP=110*1024*1024
MAX_FILES={"current.apk","current.json"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def github(token: str, path: str, *, download: bool=False) -> bytes:
    if not path.startswith("/repos/"+REPO+"/"):
        raise ValueError("Unexpected GitHub API path")
    req=urllib.request.Request(API+path,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"epimediahub-admin-update-sync/1",
    })
    opener=urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req,timeout=20) as response:
            if not download:
                return response.read(256*1024+1)
            return response.read(MAX_ZIP+1)
    except urllib.error.HTTPError as ex:
        if not download or ex.code not in (301,302,303,307,308):
            raise
        url=ex.headers.get("Location","")
        u=urllib.parse.urlparse(url)
        if u.scheme!="https" or not u.hostname or u.username or u.password:
            raise ValueError("Unsafe artifact redirect")
        # Deliberately do NOT forward GitHub bearer credentials off GitHub API.
        unsigned=urllib.request.Request(url,headers={
            "User-Agent":"epimediahub-admin-update-sync/1"
        })
        with urllib.request.urlopen(unsigned,timeout=30) as response:
            return response.read(MAX_ZIP+1)


def json_endpoint(token: str, path: str):
    data=github(token,path)
    if len(data)>256*1024:
        raise ValueError("Oversized GitHub response")
    return json.loads(data)


def latest_signed_artifact(token: str):
    runs=json_endpoint(token,
        "/repos/"+REPO+"/actions/workflows/"+WORKFLOW+
        "/runs?branch=main&status=success&per_page=10")
    for run in runs.get("workflow_runs",[])[:10]:
        if (run.get("name")!="EpiMediaHub Admin private signed release" or
            run.get("head_branch")!="main" or run.get("event")!="workflow_dispatch" or
            run.get("status")!="completed" or run.get("conclusion")!="success"):
            continue
        ident=run.get("id")
        if type(ident) is not int:continue
        found=json_endpoint(token,"/repos/"+REPO+
            "/actions/runs/"+str(ident)+"/artifacts?per_page=25")
        for artifact in found.get("artifacts",[])[:25]:
            aid=artifact.get("id")
            if (artifact.get("name")==ARTIFACT and artifact.get("expired") is False
                and type(aid) is int and aid>0 and
                type(artifact.get("size_in_bytes")) is int and
                1000 <= artifact["size_in_bytes"]<=MAX_ZIP):
                return aid
    return None


def unpack_safe(payload:bytes,destination:Path):
    if len(payload)>MAX_ZIP:
        raise ValueError("Oversized Admin release archive")
    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        entries=[i for i in bundle.infolist() if not i.is_dir()]
        if {i.filename for i in entries}!=MAX_FILES or len(entries)!=2:
            raise ValueError("Unexpected Admin release archive entries")
        for entry in entries:
            if (entry.file_size>100*1024*1024 or entry.file_size<=0 or
                (entry.external_attr>>16)&0o170000==0o120000):
                raise ValueError("Unsafe archive entry")
            target=destination/entry.filename
            with bundle.open(entry) as src,target.open("xb") as dst:
                os.fchmod(dst.fileno(),0o600)
                while block:=src.read(256*1024):
                    dst.write(block)


def sync(directory:Path):
    if (directory.is_symlink() or not directory.is_dir()
        or directory.stat().st_mode&0o077
        or directory.stat().st_uid!=os.geteuid()):
        raise PermissionError("Private Admin directory unsafe")
    token_path=directory/"github-actions.token"
    if (not token_path.is_file() or token_path.is_symlink() or
        token_path.stat().st_uid!=os.geteuid() or
        token_path.stat().st_mode&0o077):
        raise PermissionError("Private Actions read-token not configured")
    token=token_path.read_text(encoding="utf-8").strip()
    if len(token)<35 or len(token)>250 or "\n" in token:
        raise ValueError("Invalid Actions read-token")
    artifact=latest_signed_artifact(token)
    if artifact is None:
        return {"status":"NO_NEW_SIGNED_ADMIN_ARTIFACT"}
    data=github(token,"/repos/"+REPO+"/actions/artifacts/"+
                str(artifact)+"/zip",download=True)
    with tempfile.TemporaryDirectory(prefix=".admin-update-",dir=directory) as temp:
        staging=Path(temp)
        os.chmod(staging,0o700)
        unpack_safe(data,staging)
        try:
            output=publish(staging,directory)
        except ValueError as exc:
            if str(exc)=="Refusing downgrade or repeated release":
                return {"status":"ADMIN_ALREADY_AT_OR_ABOVE_ARTIFACT"}
            raise
    return {"status":"ADMIN_SIGNED_ARTIFACT_PUBLISHED",
            "version_code":output["version_code"],"private_only":True}


def main():
    base=Path(os.environ.get("EPIMEDIAHUB_DATA_DIR","/var/lib/epimediahub"))
    folder=base/"admin-mobile"
    print(json.dumps(sync(folder),sort_keys=True))


if __name__=="__main__":
    main()
