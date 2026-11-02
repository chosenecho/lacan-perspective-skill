#!/usr/bin/env python3
"""Validate portable skill structure, or additionally the private research corpus.

Structural checks are not semantic/clinical validation. --with-corpus verifies
recorded local hashes and literal short quotations on their recorded file page.
The corpus is intentionally absent from public distributions.
"""
from pathlib import Path
import argparse, datetime as dt, hashlib, json, re, sys, unicodedata
from urllib.parse import unquote
ROOT=Path(__file__).resolve().parents[1]
PAGE=re.compile(r'(?:\[\[PDF_PAGE_(\d+)\]\]|\[PDF PAGE (\d+)\])')

def norm(s):
    s=unicodedata.normalize('NFC',s).replace('’',"'").replace('‘',"'")
    return re.sub(r'\s+',' ',s).strip()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--with-corpus',action='store_true')
    ap.add_argument('--report',default='.tmp/package-check.json')
    args=ap.parse_args(); checks=[];warnings=[]
    def check(name,ok,detail=None):
        checks.append({'check':name,'passed':bool(ok),'detail':detail})
    skill=(ROOT/'SKILL.md').read_text(encoding='utf-8-sig')
    fm=re.match(r'^---\n(.*?)\n---\n',skill,re.S)
    check('frontmatter_present',fm is not None)
    if fm:
        try:
            import yaml
            data=yaml.safe_load(fm.group(1))
            check('yaml_name',data.get('name')=='lacan-perspective')
            desc=data.get('description','')
            check('yaml_description',isinstance(desc,str) and 0<len(desc)<=1024)
            check('yaml_keys',set(data)<={'name','description','license','allowed-tools','metadata'})
        except ImportError:
            warnings.append('PyYAML unavailable: full YAML parse skipped; run skill-creator quick_validate when available')
    check('entrypoint_progressive_disclosure',len(skill.splitlines())<500,{'lines':len(skill.splitlines()),'bytes':len(skill.encode('utf-8'))})
    blocks=re.findall(r'^### M[1-7].*?(?=^### M|^## |\Z)',skill,re.M|re.S)
    check('seven_models',len(blocks)==7)
    check('model_operational_fields',all(all(k in b for k in ('观察入口','操作','成立条件','失效条件','依据')) for b in blocks))
    h=skill.split('## 十条判断启发式',1)[1].split('## 表达',1)[0]
    check('ten_heuristics',len([x for x in h.splitlines() if x.startswith('|')])-2==10)
    check('no_entrypoint_placeholders',not re.search(r'\[TODO|\[PLACEHOLDER|待填写',skill,re.I))
    six=[]
    for n in range(1,7):
        fs=list((ROOT/'references/research').glob(f'{n:02d}-*.md'))
        count=sum(len(re.findall(r'[\u4e00-\u9fff]',f.read_text(encoding='utf-8'))) for f in fs)
        six.append({'dimension':n,'files':[f.name for f in fs],'han_characters':count})
        check(f'research_dimension_{n}',len(fs)==1 and count>=2000,six[-1])
    broken=[];raw_links=[];link_count=0
    files=[ROOT/'SKILL.md',ROOT/'README.md']+list((ROOT/'references').rglob('*.md'))
    for f in files:
        if any(p in f.relative_to(ROOT).parts for p in ('books','transcripts','articles')):continue
        content=f.read_text(encoding='utf-8-sig')
        for m in re.finditer(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',content):
            target=m.group(1).strip().split(' "',1)[0].strip('<>')
            if re.match(r'(?:https?://|mailto:|#)',target):continue
            local=unquote(target.split('#',1)[0])
            if not local:continue
            link_count+=1;dest=f.parent/local
            if not dest.exists():broken.append({'file':f.relative_to(ROOT).as_posix(),'target':target})
            if any(p in dest.parts for p in ('books','transcripts','articles')):raw_links.append(target)
    check('local_markdown_links',not broken,{'checked':link_count,'broken':broken})
    if raw_links:warnings.append('Some links require private source files: '+str(raw_links))
    catalog=json.loads((ROOT/'references/sources/catalog.json').read_text(encoding='utf-8'))
    sources={r['id']:r for r in catalog['sources']}
    check('unique_source_ids',len(sources)==len(catalog['sources']))
    units={}
    for r in sources.values():
        if r.get('substantively_used'):units.setdefault(r['study_unit'],[]).append(r)
    primary=sum(any(r.get('lacan_primary') for r in group) for group in units.values())
    check('primary_majority_explicit_units',bool(units) and primary/len(units)>.5,{'primary_units':primary,'all_substantive_units':len(units),'ratio':primary/len(units) if units else None,'not_a_word_or_page_ratio':True})
    qbank=json.loads((ROOT/'references/verified-quotes.json').read_text(encoding='utf-8'))
    check('quote_source_ids',all(q['source_id'] in sources for q in qbank['quotes']))
    if args.with_corpus:
        failures=[];verified={}
        for sid,r in sources.items():
            if not r.get('local_file_available'):continue
            f=ROOT/r['path']
            if not f.is_file():failures.append({'id':sid,'reason':'missing file'});continue
            digest=hashlib.sha256(f.read_bytes()).hexdigest()
            if digest!=r['sha256']:failures.append({'id':sid,'reason':'sha256 mismatch'})
            verified[digest]=str(f)
        check('private_corpus_hashes',not failures,{'distinct_files':len(verified),'failures':failures})
        quoted=[]
        for q in qbank['quotes']:
            r=sources[q['source_id']];f=ROOT/r['text_path']
            text=f.read_bytes().decode('utf-8'); scope=text
            if q.get('pdf_file_page'):
                markers=list(PAGE.finditer(text));scope=''
                for i,m in enumerate(markers):
                    if int(m.group(1) or m.group(2))==q['pdf_file_page']:
                        scope=text[m.end():markers[i+1].start() if i+1<len(markers) else len(text)];break
            ok=norm(q['text']) in norm(scope)
            quoted.append({'id':q['id'],'source_id':q['source_id'],'file_page':q.get('pdf_file_page'),'literal_match':ok})
        check('literal_quote_page_matches',all(q['literal_match'] for q in quoted),quoted)
    else:
        warnings.append('Private corpus hashes and literal page matches not checked; use --with-corpus only where raw sources are available')
    passed=all(r['passed'] for r in checks)
    report={'checked_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'with_private_corpus':args.with_corpus,'passed':passed,'checks':checks,'warnings':warnings,'limitation':'Structural/hash/literal checks do not validate historical interpretation, style quality, clinical efficacy or all possible responses.'}
    out=ROOT/args.report;out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if passed else 1

if __name__=='__main__':sys.exit(main())
