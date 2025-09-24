import os
import requests
import json
import zipfile
import sqlite3
import pandas as pd
import time

# --- Configuração ---
# O login agora é feito através de um cookie de sessão para maior fiabilidade
ANKIWEB_COOKIE = os.environ.get("ANKIWEB_SESSION_COOKIE")
DECK_NAME = os.environ.get("DECK_NAME", "Default")

# --- Caminhos de Arquivos ---
OUTPUT_DIR = "public"
DB_PATH = os.path.join(OUTPUT_DIR, "collection.anki2")
HTML_PATH = os.path.join(OUTPUT_DIR, "index.html")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def anki_download_with_cookie():
    """Baixa a coleção do AnkiWeb usando um cookie de sessão em vez de login."""
    if not ANKIWEB_COOKIE:
        raise Exception("O 'Secret' ANKIWEB_SESSION_COOKIE não foi configurado no GitHub.")

    print("Configurando a sessão de download com o cookie...")
    session = requests.Session()
    
    # Adiciona o cookie à sessão
    session.cookies.set('ankiweb', ANKIWEB_COOKIE, domain='.ankiweb.net')
    
    # Adiciona um User-Agent para parecer um navegador normal
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    print("Baixando a coleção de baralhos...")
    download_url = "https://ankiweb.net/decks/download"
    try:
        response = session.get(download_url, stream=True, headers=headers, timeout=60)
        
        if response.status_code != 200:
            print(f"--- DEBUG INFO ---")
            print(f"Status Code: {response.status_code}")
            print(f"URL: {response.url}")
            print(f"Response Text (início): {response.text[:500]}")
            print(f"--------------------")
            raise Exception(f"Não foi possível baixar a coleção. O cookie pode ser inválido ou ter expirado.")

        zip_path = os.path.join(OUTPUT_DIR, "collection.apkg")
        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("Download da coleção concluído.")

    except requests.exceptions.RequestException as e:
        raise Exception(f"Ocorreu um erro de rede durante o download: {e}")


    print("Extraindo a coleção...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(OUTPUT_DIR)
    print("Extração concluída.")
    os.remove(zip_path)

def extract_cards_from_db():
    """Extrai os cartões do baralho especificado do banco de dados SQLite."""
    print(f"Conectando ao banco de dados: {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    
    try:
        decks_df = pd.read_sql_query("SELECT id, name FROM decks", con)
        deck_id = decks_df[decks_df['name'] == DECK_NAME]['id'].iloc[0]
        print(f"ID do baralho '{DECK_NAME}' encontrado: {deck_id}")
    except (IndexError, pd.io.sql.DatabaseError):
        con.close()
        raise Exception(f"Baralho com o nome '{DECK_NAME}' não encontrado. Verifique o nome.")

    query = f"SELECT n.flds FROM cards c JOIN notes n ON c.nid = n.id WHERE c.did = {deck_id}"
    cards_df = pd.read_sql_query(query, con)
    con.close()
    
    cards_list = []
    for flds in cards_df['flds']:
        parts = flds.split('\x1f')
        if len(parts) >= 2:
            cards_list.append({"front": parts[0], "back": parts[1]})
            
    print(f"{len(cards_list)} cartões extraídos com sucesso.")
    return cards_list

def generate_html(cards):
    """Gera o arquivo HTML final do visualizador."""
    print("Gerando o arquivo HTML final...")
    card_data_string = json.dumps(cards)
    
    html_template = f"""
<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Visualizador Anki - {DECK_NAME}</title>
<style>body{{font-family:Arial,sans-serif;background-color:#f0f0f0;color:#000;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;padding:10px;box-sizing:border-box}}#app{{width:100%;max-width:800px;text-align:center}}.flashcard{{background-color:#fff;border:2px solid #000;padding:20px;min-height:300px;display:flex;flex-direction:column;justify-content:center;align-items:center;font-size:1.5em;margin-bottom:20px;box-shadow:0 4px 6px rgba(0,0,0,0.1);word-wrap:break-word;overflow-y:auto}}.flashcard-back{{display:none}}.controls{{display:flex;justify-content:center;gap:10px;flex-wrap:wrap}}button{{background-color:#fff;color:#000;border:2px solid #000;padding:15px 25px;font-size:1em;cursor:pointer;font-weight:bold;box-shadow:2px 2px 0 #000}}button:disabled{{background-color:#ccc;color:#888;cursor:not-allowed;box-shadow:none}}#counter{{margin-top:20px;font-size:1.2em;font-weight:bold}}</style>
</head><body>
<div id="app"><div id="flashcard" class="flashcard"><div id="card-front"></div><div id="card-back" class="flashcard-back"></div></div><div class="controls"><button id="btn-prev" disabled>Anterior</button><button id="btn-reveal">Mostrar Resposta</button><button id="btn-next" disabled>Próximo</button></div><div id="counter"></div></div>
<script>
document.addEventListener('DOMContentLoaded',()=>{{const t=document.getElementById("card-front"),e=document.getElementById("card-back"),n=document.getElementById("btn-prev"),o=document.getElementById("btn-reveal"),d=document.getElementById("btn-next"),c=document.getElementById("counter"),r={card_data_string};let i=0,a=!1;function s(l){{if(r&&0!==r.length&&!(l<0||l>=r.length)){{i=l,a=!1;const s=r[i];t.innerHTML=s.front.replace(/\\n/g,"<br>"),e.innerHTML=s.back.replace(/\\n/g,"<br>"),e.style.display="none",o.textContent="Mostrar Resposta",c.textContent=`Cartão ${{i+1}} de ${{r.length}}`,n.disabled=0===i,d.disabled=i===r.length-1}}else t.textContent="Nenhum cartão carregado."}}o.addEventListener("click",()=>{{a=!a,e.style.display=a?"block":"none",o.textContent=a?"Ocultar Resposta":"Mostrar Resposta"}}),d.addEventListener("click",()=>{{i<r.length-1&&s(i+1)}}),n.addEventListener("click",()=>{{i>0&&s(i-1)}}),s(0)}});
</script>
</body></html>"""

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"Arquivo HTML salvo em: {HTML_PATH}")

if __name__ == "__main__":
    # Removemos a necessidade do Selenium e do login, usando o cookie diretamente
    anki_download_with_cookie()
    extracted_cards = extract_cards_from_db()
    generate_html(extracted_cards)



