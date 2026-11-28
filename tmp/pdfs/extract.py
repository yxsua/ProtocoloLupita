from pypdf import PdfReader
from pathlib import Path
files = {
'convocatoria': Path(r'C:\Users\hoshi\Documents\9 - Noveno Semestre\Hackathon_Bloque\Información_Investigacion\Convocatoria_Hackathon.pdf'),
'propuesta': Path(r'C:\Users\hoshi\Documents\9 - Noveno Semestre\Hackathon_Bloque\Información_Investigacion\Proyecto_Propuesto.pdf'),
'ideas': Path(r'C:\Users\hoshi\Documents\9 - Noveno Semestre\Hackathon_Bloque\Información_Investigacion\Ideas e Investigación - Hackathon Bloque.pdf')}
out=Path('tmp/pdfs')
for name,path in files.items():
    reader=PdfReader(str(path))
    target=out/f'{name}.txt'
    target.write_text('\n\n'.join(f'===== PÁGINA {i+1} =====\n{p.extract_text() or ""}' for i,p in enumerate(reader.pages)),encoding='utf-8')
    print(f'{name}: {len(reader.pages)} páginas, {target.stat().st_size} bytes')
    for i,p in enumerate(reader.pages[:2]):
        print(f'--- {name} página {i+1} ---')
        print((p.extract_text() or '')[:2500])
