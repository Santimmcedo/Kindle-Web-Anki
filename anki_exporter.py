import os
import requests
import json
import zipfile
import sqlite3
import pandas as pd
import time

# Importações do Selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# --- Configuração ---
ANKIWEB_USERNAME = os.environ.get("ANKIWEB_USERNAME")
ANKIWEB_PASSWORD = os.environ.get("ANKIWEB_PASSWORD")
DECK_NAME = os.environ.get("DECK_NAME", "Default")

# --- Caminhos de Arquivos ---
OUTPUT_DIR = "public"
DB_PATH = os.path.join(OUTPUT_DIR, "collection.anki2")
HTML_PATH = os.path.join(OUTPUT_DIR, "index.html")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def anki_login_and_download():
    """Faz login no AnkiWeb usando um navegador real (Selenium) e baixa a coleção."""
    print("Configurando o navegador headless...")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=options)
    
    try:
        print("Navegando para a página de login do AnkiWeb...")
        driver.get("https://ankiweb.net/account/login")

        # Espera até que os campos de login estejam presentes
        wait = WebDriverWait(driver, 15)
        
        print("Preenchendo o formulário de login...")
        email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
        password_field = wait.until(EC.presence_of_element_located((By.ID, "password")))
        
        email_field.send_keys(ANKIWEB_USERNAME)
        password_field.send_keys(ANKIWEB_PASSWORD)
        
        print("Submetendo o formulário...")
        login_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn-primary")))
        login_button.click()
        
        # Espera pelo redirecionamento para a página de baralhos como confirmação de login
        wait.until(EC.url_contains("/decks/"))
        print("Login bem-sucedido.")

        # ATUALIZAÇÃO: Usa os cookies do Selenium para baixar com o 'requests'
        print("Extraindo cookies da sessão do navegador...")
        selenium_cookies = driver.get_cookies()
        
        # Cria uma sessão 'requests' para o download
        session = requests.Session()
        for cookie in selenium_cookies:
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])

        print("Baixando a coleção de baralhos...")
        download_url = "https://ankiweb.net/decks/download"
        response = session.get(download_url, stream=True, headers={'User-Agent': 'Mozilla/5.0'})
        
        if response.status_code != 200:
            raise Exception(f"Não foi possível baixar a coleção. Status: {response.status_code}")

        zip_path = os.path.join(OUTPUT_DIR, "collection.apkg")
        with open(zip_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("Download da coleção concluído.")
        
    except TimeoutException:
        print("--- DEBUG INFO (SELENIUM) ---")
        print(f"URL atual: {driver.current_url}")
        print("Ocorreu um Timeout. A página pode ter mudado ou o login falhou.")
        driver.save_screenshot("debug_screenshot.png") # Salva uma imagem para depuração
        print(f"Screenshot salvo como 'debug_screenshot.png' nos artifacts da Action.")
        print("-----------------------------")
        raise Exception("Falha no login do AnkiWeb (Timeout). Verifique as credenciais ou a estrutura da página.")
    finally:
        driver.quit()

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
    anki_login_and_download()
    extracted_cards = extract_cards_from_db()
    generate_html(extracted_cards)




