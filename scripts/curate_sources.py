#!/usr/bin/env python3
"""Reproduce the explicit reading-unit curation for the 2026-11-03 study.

This is an auditable editorial decision, not an inference that a download was
read. Catalogue records, unread material and failed sources do not inflate the
substantive-text denominator. Criticism and institutional accounts are never
classified as Lacan-authored primary texts.
"""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'references/sources'

def rows(name):
    return [json.loads(s) for s in (BASE/'manifests'/name).read_text(encoding='utf-8-sig').splitlines() if s.strip()]

def main():
    annotations = {}
    def put(r, unit=None, primary=False, used=False, reason='metadata, unread, failed or contextual locator only'):
        sid = r['id']
        annotations[sid] = {
            'study_unit': unit or sid, 'lacan_primary': primary,
            'substantively_used': used, 'curation_reason': reason,
            'curated_as_of': '2026-11-03',
            **{k:r[k] for k in ('reading_status','reading_scope','bibliographic_unit_id','version_note') if k in r}}
    writings = {}
    for r in rows('writings.jsonl'):
        if r.get('reading_status') in ('full_text_read','selected_passages_read'):
            writings[r['id']] = r
    wunits = {'W06e':'W06','W06-fr':'W06','W07':'SEMINAR-11','W08':'SEMINAR-17',
              'W09':'SEMINAR-20','W10':'SEMINAR-22','W11':'SEMINAR-23','W15':'SEMINAR-7'}
    for sid,r in writings.items():
        put(r,wunits.get(sid,sid),True,True,'Authoritative writings reading receipt; editions of the same work share a unit')
    full_c = {'C01','C02','C03','C06','C07c','C08','C11','C13c','C15'}
    for r in rows('conversations.jsonl'):
        sid=r['id']; used=sid in full_c
        put(r,sid,sid in full_c,used,'Nine substantively read interview/lecture units; edited/transcribed mediation retained' if used else 'Not a separate high-confidence substantive dialogue: see scope and version note')
    for r in rows('criticism.jsonl'):
        used=r['id']!='E03'
        put(r,r['id'],False,used,'Critic/scholar text substantively used within specified scope; E08 via web with local download failed' if used else 'Bibliographic record only; Derrida essay not obtained')
    dunits={'D05':'PROPOSITION-1967','D06':'PROPOSITION-1967','D24':'W01','D25':'W03','D26':'SEMINAR-11','D27':'C07c',
            'D28':'E09','D29':'D11','D30':'C08','D31':'SEMINAR-17'}
    for r in rows('decisions.jsonl'):
        sid=r['id']; used=sid not in {'D16','D18','D21','D23','D32'}
        put(r,dunits.get(sid,sid),bool(r.get('lacan_primary')),used,'Action-study reading receipt; shared works and dissolution witnesses deduplicated' if used else 'Metadata only, failed or archived unread')
    tunits={'T01':'E05','T02':'W01','T03':'W02','T04':'W03','T06':'D13','T07':'D04',
            'T08':'PROPOSITION-1967','T09':'PROPOSITION-1967','T10':'D14','T11':'D09','T13':'D11','T16':'D15','T28':'C18'}
    # Bibliographical fields remain evidence for dates but are explicitly
    # outside this ratio of substantive argument/document reading units.
    t_used={'T01','T02','T03','T04','T05','T06','T07','T09','T10','T13','T14','T15','T16','T18','T22','T26','T35'}
    t_primary={'T02','T03','T04','T07','T09','T13','T14','T15'}
    for r in rows('timeline.jsonl'):
        sid=r['id']
        put(r,tunits.get(sid,sid),sid in t_primary,sid in t_used,'Substantive historical passage/document actually read; Lacan authorship separately classified' if sid in t_used else 'Bibliographic/programme/date fields, crosscheck-only, excluded identity or unavailable source; not substantive-text denominator')
    for r in rows('voice.jsonl'):
        sid=r['id']
        if sid=='STA-S13':
            put(r,'SEMINAR-13',True,True,'Three complete sampled passages plus context; not entire seminar')
        # Other voice receipts reuse the earlier work identities and do not
        # overwrite their fuller authoritative reading scopes.
    # Archive aliases participate only when substantive reading was documented.
    for n,work in [(7,'W15'),(11,'W07'),(17,'W08'),(20,'W09'),(22,'W10'),(23,'W11')]:
        if work in writings:
            r=dict(writings[work]);r['id']=f'STA-S{n}'
            put(r,f'SEMINAR-{n}',True,True,'Archive alias for an explicitly read seminar; same study unit')
    out=BASE/'source-annotations.json'
    out.write_text(json.dumps(annotations,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'curated_source_ids':len(annotations),'note':'Historical-text unit ratio, not page/word ratio or archive-download ratio'},ensure_ascii=False))

if __name__=='__main__':main()
