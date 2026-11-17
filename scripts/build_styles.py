"""Build one product stylesheet, preserving the documented cascade order."""
from pathlib import Path
from hashlib import sha256
import re

root=Path(__file__).resolve().parents[1]/'src/app/static'
parts=['product-base.css','company-media.css','theme.css','workspace.css','liquidity-brief.css','workspace-refinement.css','product-polish.css','workspace-transitions.css','stock-focus.css']
output='\n\n'.join('/* '+name+' */\n'+(root/name).read_text(encoding='utf8') for name in parts)+'\n'
(root/'product.css').write_text(output,encoding='utf8')
index=root/'index.html';html=index.read_text(encoding='utf8')
html=re.sub(r'href="/product\.css(?:\?v=[a-f0-9]+)?"','href="/product.css?v='+sha256(output.encode()).hexdigest()[:10]+'"',html)
index.write_text(html,encoding='utf8')
print('Built combined product stylesheet')
