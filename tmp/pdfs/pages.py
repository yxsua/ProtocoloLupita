from pathlib import Path
for fn in ['convocatoria','propuesta','ideas']:
 text=Path(f'tmp/pdfs/{fn}.txt').read_text(encoding='utf-8')
 pages=text.split('===== PÁGINA ')
 print('\n###',fn)
 for idx,page in enumerate(pages[1:],1):
  body=page.split('=====\n',1)[-1].strip().replace('\n',' ')
  print(f'{idx:02}: {body[:420]}')
