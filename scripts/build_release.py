#!/usr/bin/env python3
'''Build a deterministic portable release from tracked original files.

Run from a clean committed tree. Third-party raw source directories
are forbidden even if accidentally tracked. Output stays in ignored .tmp/.
'''
from pathlib import Path
import argparse, datetime as dt, hashlib, json, subprocess, zipfile

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {'books', 'transcripts', 'articles', '.tmp', '.git', '__pycache__'}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', default='.tmp/dist')
    args = ap.parse_args()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise SystemExit('Commit intended files and leave a clean tree before building a release')
    skill = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
    version_lines = [s for s in skill.splitlines() if s.strip().startswith('version:')]
    if len(version_lines) != 1:
        raise SystemExit('Expected one version in SKILL metadata')
    version = version_lines[0].split(':', 1)[1].strip().strip(chr(34)).strip(chr(39))
    if len(version.split('.')) != 3 or not all(p.isdigit() for p in version.split('.')):
        raise SystemExit('Expected a three-part numeric semantic version')
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split(chr(0))
    files = sorted(p for p in tracked if p)
    for rel in files:
        path = Path(rel)
        if path.is_absolute() or '..' in path.parts or FORBIDDEN.intersection(path.parts):
            raise SystemExit('Forbidden release path: ' + rel)
        if (ROOT / path).is_symlink():
            raise SystemExit('Do not package symlinks: ' + rel)
        if not (ROOT / path).is_file():
            raise SystemExit('Missing tracked file: ' + rel)
    for required in ['SKILL.md', 'README.md', 'LICENSE', 'agents/openai.yaml', 'references/research/08-research-review.md']:
        if required not in files:
            raise SystemExit('Required file not tracked: ' + required)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    epoch = int(subprocess.check_output(['git', 'show', '-s', '--format=%ct', 'HEAD'], cwd=ROOT, text=True).strip())
    stamp = dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
    ztime = (max(stamp.year, 1980), stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second)
    out = Path(args.output)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f'lacan-perspective-v{version}.zip'
    manifest = []
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in files:
            data = subprocess.check_output(['git', 'show', 'HEAD:' + rel], cwd=ROOT)
            manifest.append(hashlib.sha256(data).hexdigest() + '  ' + rel)
            info = zipfile.ZipInfo('lacan-perspective/' + rel, date_time=ztime)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
        info = zipfile.ZipInfo('lacan-perspective/PACKAGE-MANIFEST.sha256', date_time=ztime)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        z.writestr(info, chr(10).join(manifest) + chr(10))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sums = archive.with_suffix('.zip.sha256')
    sums.write_text(digest + '  ' + archive.name + chr(10), encoding='utf-8')
    print(json.dumps({'archive': str(archive), 'sha256_file': str(sums), 'sha256': digest, 'files': len(files), 'bytes': archive.stat().st_size, 'source_commit': commit, 'note': 'Files read from Git commit blobs, independent of checkout line endings.'}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
