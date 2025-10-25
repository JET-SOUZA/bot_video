# checa_cookies.py
from pathlib import Path
p = Path("cookies.txt")
if not p.exists():
    print("ERRO: cookies.txt não encontrado na pasta atual.")
    raise SystemExit(1)
text = p.read_text(encoding="utf-8", errors="replace")
print("=== Primeiras 20 linhas de cookies.txt ===")
for i, line in enumerate(text.splitlines()[:20], 1):
    print(f"{i:02d}: {line}")
print("=========================================")
needed = ["sessionid", "sid_tt", "tt_webid", "s_v_web_id", "msToken", "odin_tt"]
print("Presença de tokens importantes:")
for k in needed:
    print(f" - {k}: {'OK' if k in text else 'NÃO ENCONTRADO'}")
