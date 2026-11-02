'''Reproduce the 20-passage purposive voice study without external packages.

Run from any directory with Python 3: analyze_voice.py [--check].
Source files are read as bytes then decoded with their original newlines intact.
The output contains locators, hashes and metrics, never full source passages.
Sentence segments and lexical markers are surface counts, not style essences.
'''
from pathlib import Path
import re, json, hashlib, statistics, argparse
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'references/voice-analysis.json'
PAGE=re.compile(r'(?:\[\[PDF_PAGE_(\d+)\]\]|\[PDF PAGE (\d+)\])')
WORD=re.compile(r'[^\W\d_]+(?:[’\x27][^\W\d_]+)*(?:[-‑][^\W\d_]+(?:[’\x27][^\W\d_]+)*)*',re.UNICODE)
SOURCES={
'C01':('newspaper_interview','1957-05-31','references/sources/transcripts/conversations/C01-Chapsal_LExpress_1957.txt'),
'W12':('published_paper','1965-12-01 / published 1966','references/sources/articles/writings/W12-science-truth-1966.txt'),
'STA-S13':('live_seminar','1966-01-05','references/sources/books/staferla/S13.txt'),
'C07c':('prepared_television','recorded 1973 / broadcast 1974','references/sources/transcripts/conversations/C07c-Television_literal.txt'),
'C08':('press_conference','1974-10-29','references/sources/transcripts/conversations/C08-Rome_presse_1974.txt'),
'C11':('peer_questions','1975-11-24 / published 1976','references/sources/transcripts/conversations/C11-Yale_Kanzer_1975.txt'),
'C13c':('clinical_lecture_questions','1975-10-04 / 1985 working text','references/sources/articles/conversations/C13c-Geneve_1975.txt')}
# Exactly one complete typeset paragraph or short answer paragraph per sample.
# Anchors locate original sources; full source passages are never written.
SPEC=[
('V01','C01',2,'Savoir qu’il y a','à une puissance seconde.','analogy','Champollion; bounded comparison'),
('V02','C01',2,'Voyez les hiéroglyphes égyptiens','auquel il appartient.','analogy','writing system and isolated signs'),
('V03','C01',3,'Le terme de « censure','exprimé dans un langage.','analogy','censorship/scissors and repression'),
('V04','W12',None,'Mais pour qu’il sache','égale à sa tache.','none','empirical fact versus constituted object'),
('V05','W12',None,'Ce fil ne nous','viennent se conjoindre.','formal_model','Moebius model; not just an illustration'),
('V06','W12',None,'Nous disons, contrairement','à jamais son nom.','none','long historical counterclaim'),
('V07','STA-S13',68,'Je suis venu de loin','qui s’appelle le moi.','metaphor','gold thread; long retrospective sentence'),
('V08','STA-S13',68,'Je ne l’ai pas appelé','l’aliénation fondamentale.','explicit_example','alternative i(s) notation; self correction'),
('V09','STA-S13',69,'Que nous sommes déjà récompensés','que l’homme atteint ?','none','exclamation then a classroom question'),
('V10','C07c',3,'Je dis toujours la vérité','vérité touche au réel.','none','assertion interrupted and qualified; editorial insertion removed'),
('V11','C07c',10,'Un saint - pour me faire comprendre','ce que je dis.','analogy','saint and refuse; prepared analogy'),
('V12','C07c',10,'Qu’on me réponde seulement','pensée que ça décharge.','explicit_example','three rhetorical questions; adrenaline example'),
('V13','C08',7,'Alors je ne suis pas','servi pour ça.','none','cannot verify translation; sarcasm retained'),
('V14','C08',7,'Et puis je vais','vaut ce qu’elle vaut.','analogy','paper flowers; self promotion retained'),
('V15','C08',12,'Ce à quoi je m’efforce','pas le moins du monde.','analogy','limited clinical basis; handrail/stairs analogy'),
('V16','C11',12,'Jusqu’à présent, tout','l’usage de petites lettres.','explicit_example','formula and electrons; science claims not validated here'),
('V17','C11',12,'Il est certain que j’essaie','ces petites lettres.','analogy','nucleus and scientific letters; first complete paragraph'),
('V18','C11',12,'Je n’ai pas dit tout','un minimum mathématisable.','none','short corrective answer limits a formulation'),
('V19','C13c',None,'Je ne suis pas absolument sûr','n’est pas encore arrivé.','none','revisability; boast retained'),
('V20','C13c',None,'– Il est certain que c’est','sentiment comme analystes.','analogy','written body; unexplored clinical conjecture')]

def sha(value): return hashlib.sha256(value).hexdigest()
def normalize(raw):
 chars,offsets=[],[]
 for m in re.finditer(r'\S+',raw):
  if chars: chars.append(' '); offsets.append(m.start())
  chars.extend(m.group()); offsets.extend(range(m.start(),m.end()))
 return ''.join(chars),offsets
def clean(raw):
 result,depth,removed=[],0,0
 for c in raw:
  if c=='[': depth+=1; removed+=1
  elif c==']' and depth: depth-=1
  elif not depth: result.append(c)
 if depth: raise ValueError('Unclosed editor bracket')
 value=re.sub(r'(?<!\w)\(\d{1,3}\)(?=[A-Za-zÀ-ÿ])','',''.join(result))
 return re.sub(r'\s+',' ',value).strip(),removed
def segments(value,ellipsis=False):
 if not ellipsis: value=re.sub(r'\.{2,}|…+','§',value)
 value=re.sub(r'\b(?:Mme|Mlle|Dr|Pr|cf|etc|pp?|av|M)\.',lambda m:m.group().replace('.','¤'),value,flags=re.I)
 return [len(WORD.findall(s)) for s in re.split(r'[.!?…]+',value) if WORD.search(s)]
def count(p,t): return len(re.findall(p,t,re.I))
def metrics(t):
 ls=segments(t)
 contrast={w:count(r'(?<!\w)'+w+r'(?!\w)',t) for w in ['mais','pourtant','cependant','néanmoins','toutefois','or','au contraire','en revanche']}
 figures={w:count(r'(?<!\w)'+w+r'(?!\w)',t) for w in ['comme','par exemple','comparaison','de la même façon','à la façon']}
 return dict(words=len(WORD.findall(t)),sentence_segments=len(ls),sentence_word_lengths=ls,mean_words_per_segment=round(statistics.mean(ls),3),median_words_per_segment=statistics.median(ls),segments_if_ellipsis_is_boundary=len(segments(t,True)),question_marks=t.count('?'),first_person_singular_markers=count(r'(?<!\w)(?:je|me|moi)(?!\w)|(?<!\w)[jm][’\x27](?=\w)',t),first_person_plural_nous=count(r'(?<!\w)nous(?!\w)',t),contrast_markers=contrast,contrast_marker_total=sum(contrast.values()),analogy_surface_markers=figures,analogy_surface_marker_total=sum(figures.values()))
def locate(source,page,start,end):
 base,limit=0,len(source)
 if page is not None:
  marks=list(PAGE.finditer(source)); ix=[i for i,m in enumerate(marks) if int(m.group(1) or m.group(2))==page]
  if len(ix)!=1: raise ValueError(('page',page,len(ix)))
  i=ix[0]; base=marks[i].end(); limit=marks[i+1].start() if i+1<len(marks) else len(source)
 norm,offsets=normalize(source[base:limit]); a=re.sub(r'\s+',' ',start); b=re.sub(r'\s+',' ',end)
 norm=norm.replace(chr(39),'’'); a=a.replace(chr(39),'’'); b=b.replace(chr(39),'’')
 if norm.count(a)!=1: raise ValueError(('nonunique start',a,norm.count(a)))
 lo=norm.index(a); hi=norm.find(b,lo)
 if hi<0: raise ValueError(('missing end',b))
 hi+=len(b); a,b=base+offsets[lo],base+offsets[hi-1]+1
 return source[a:b],a,b
def analyze():
 sources,samples={},[]
 for sid,(genre,date,path) in SOURCES.items():
  payload=(ROOT/path).read_bytes(); sources[sid]=dict(path=path,sha256=sha(payload),genre=genre,date=date,text=payload.decode('utf-8'))
 for ident,sid,page,start,end,figure,note in SPEC:
  src=sources[sid]; raw,lo,hi=locate(src['text'],page,start,end); value,removed=clean(raw)
  if re.search(r'(?:L’EXPRESS|F\. Wolff|MME TURKELL|DR BLATT|L’Interprète)',value): raise ValueError(('non-speaker label',ident))
  samples.append(dict(id=ident,source_id=sid,genre=src['genre'],path=src['path'],pdf_file_page=page,text_lines_1_based=[src['text'].count('\n',0,lo)+1,src['text'].count('\n',0,hi)+1],raw_character_range_0_based_half_open=[lo,hi],start_marker=start,end_marker=end,raw_utf8_sha256=sha(raw.encode()),clean_utf8_sha256=sha(value.encode()),editorial_bracket_groups_removed=removed,manual_figure_label=figure,manual_annotation=note,metrics=metrics(value)))
 groups=[]
 keys=['words','sentence_segments','question_marks','first_person_singular_markers','first_person_plural_nous','contrast_marker_total','analogy_surface_marker_total','segments_if_ellipsis_is_boundary']
 for sid in SOURCES:
  ss=[s for s in samples if s['source_id']==sid]; ls=[n for s in ss for n in s['metrics']['sentence_word_lengths']]; totals={k:sum(s['metrics'][k] for s in ss) for k in keys}
  groups.append(dict(source_id=sid,genre=sources[sid]['genre'],samples=len(ss),**totals,pooled_mean_words_per_segment=round(totals['words']/totals['sentence_segments'],3),pooled_median_words_per_segment=statistics.median(ls),per_100_words={k:round(100*totals[k]/totals['words'],3) for k in keys[2:7]},manual_figure_labels=dict(Counter(s['manual_figure_label'] for s in ss))))
 return dict(schema_version=1,study_date_local='2026-11-03',design='20 purposive complete typeset paragraphs or short answer paragraphs; seven source/media groups; not a random or representative sample',selection_bias='Contrast and reusable clarification, analogy and qualification overrepresented; unequal lengths, no minimum length. Context objections read separately, excluded from speaker counts.',method=dict(tokens='French letters; internal apostrophes/hyphens stay in one token; digits excluded; no OCR split-word repair',sentences='Surface segments at .?!; ellipses suppressed as pauses; small explicit abbreviation list; semicolons/colons not boundaries. Ellipsis-boundary sensitivity retained. Not a French parser or audio analysis.',first_person='je/j-apostrophe/me/m-apostrophe/moi including quoted uses; nous separate',contrast='mais,pourtant,cependant,neanmoins,toutefois,or,au contraire,en revanche: lexical, not functional counts',figures='Surface comme/par exemple/comparaison/de la meme facon/a la facon are not semantic analogy frequency. Manual paragraph labels distinguish analogy, metaphor, formal model and example.',cleaning='Collapse whitespace; remove nested square-bracket editorial additions and selected inline original-page labels. Anchors exclude interviewer/speaker labels. JSON stores no source paragraphs.',limitations=['Edited punctuation and paragraphing; no audio timing/prosody checked','TV prepared, Yale interpreted/edited, paper originates in oral lesson; medium confounded with date/topic/editor','Regex cannot reliably resolve all French abbreviations/pauses; surface count only','Small unequal groups and long press paragraph; no significance or author-wide claim','Bracket attribution manually checked against work-transcript warnings']),sources={k:{a:b for a,b in v.items() if a!='text'} for k,v in sources.items()},sample_count=len(samples),source_count=len(sources),samples=samples,groups=groups)
def main():
 parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true'); args=parser.parse_args(); data=analyze(); rendered=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
 if args.check:
  if not OUT.exists() or OUT.read_text(encoding='utf-8')!=rendered: raise SystemExit('Stored voice analysis differs; regenerate and review')
 else: OUT.write_text(rendered,encoding='utf-8')
 print(json.dumps(dict(sample_count=data['sample_count'],source_count=data['source_count'],groups=data['groups']),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
