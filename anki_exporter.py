import os
import requests
import zipfile
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def anki_download_and_process():
    """
    Usa Selenium para lidar com a página JavaScript do AnkiWeb, obtém o CSRF token
    e depois faz o download da coleção.
    """
    cookie_value = os.environ.get("ANKIWEB_SESSION_COOKIE")
    deck_name_to_find = os.environ.get("DECK_NAME")

    if not cookie_value or not deck_name_to_find:
        raise Exception("Os 'Secrets' ANKIWEB_SESSION_COOKIE e DECK_NAME devem ser configurados.")

    # --- Parte 1: Usar Selenium para obter o CSRF token ---
    print("A configurar o navegador Chrome com Selenium...")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument('--disable-blink-features=AutomationControlled')
    
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    
    csrf_token = None
    try:
        print("A navegar para o AnkiWeb para injetar o cookie...")
        driver.get("https://ankiweb.net/decks")

        print("A injetar o cookie de sessão...")
        driver.add_cookie({
            'name': 'ankiweb',
            'value': cookie_value,
            'domain': '.ankiweb.net',
            'path': '/',
            'secure': True,
            'samesite': 'Lax'
        })

        print("A recarregar a página de baralhos (agora com login)...")
        driver.get("https://ankiweb.net/decks")
        
        # --- MUDANÇA CRUCIAL ---
        # Espera até 30 segundos que um elemento visível (o link dos baralhos) apareça.
        # Isto confirma que o login funcionou e a página renderizou.
        print("A esperar que a página seja renderizada pelo JavaScript...")
        wait = WebDriverWait(driver, 30)
        wait.until(
            EC.visibility_of_element_located((By.XPATH, "//a[contains(text(), 'Decks')]"))
        )
        print("Página de baralhos carregada com sucesso!")
        
        # Agora que a página carregou, o token DEVE estar presente.
        csrf_token_element = driver.find_element(By.CSS_SELECTOR, "input[name='csrf_token']")
        csrf_token = csrf_token_element.get_attribute('value')
        print("Token de segurança (CSRF) extraído com sucesso!")

    except Exception as e:
        print("--- DEBUG INFO (SELENIUM) ---")
        print("A página HTML no momento do erro era:")
        print(driver.page_source) # Imprime o HTML para depuração
        driver.save_screenshot("debug_screenshot.png")
        print(f"\nOcorreu um erro durante a automação do navegador: {e}")
        print("Screenshot de depuração salvo nos 'artifacts' da Action.")
        raise
    finally:
        driver.quit()

    if not csrf_token:
        raise Exception("Não foi possível extrair o CSRF token mesmo com o Selenium.")

    # --- Parte 2: Usar Requests para fazer o download ---
    print("A usar o 'requests' para baixar a coleção...")
    with requests.Session() as session:
        session.cookies.set("ankiweb", cookie_value)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://ankiweb.net/decks/",
        }
        session.headers.update(headers)
        
        export_url = "https://ankiweb.net/decks/export/apkg"
        export_data = {"csrf_token": csrf_token}
        
        download_response = session.post(export_url, data=export_data)
        download_response.raise_for_status()

        with open("collection.apkg", "wb") as f:
            f.write(download_response.content)
        print("Coleção de baralhos (.apkg) baixada com sucesso.")

    # --- Parte 3: Processar o baralho e criar o HTML (sem alterações) ---
    print(f"A processar o ficheiro .apkg para encontrar o baralho: '{deck_name_to_find}'")
    cards_html = ""
    with zipfile.ZipFile("collection.apkg", "r") as z:
        collection_data = json.loads(z.read("collection.anki21"))
        decks = {d['id']: d['name'] for d in collection_data['decks']}
        models = {m['id']: m for m in collection_data['models']}
        
        target_deck_id = next((did for did, name in decks.items() if name == deck_name_to_find), None)
        
        if not target_deck_id:
            raise Exception(f"Baralho '{deck_name_to_find}' não encontrado. Baralhos disponíveis: {list(decks.values())}")

        notes = [note for note in collection_data['notes'] if note['did'] == target_deck_id]

        for note in notes:
            model = models[note['mid']]
            fields = model['flds']
            field_values = note['flds']
            
            front_content = field_values[0]
            back_content = field_values[1] if len(field_values) > 1 else field_values[0]

            cards_html += f"""
            <div class="card">
                <div class="front">{front_content}</div>
                <div class="back">{back_content}</div>
            </div>
            """
    
    # --- Parte 4: Criar o ficheiro HTML final (sem alterações) ---
    html_template = f"""
    <!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Anki Viewer</title><style>body{{font-family:sans-serif;background-color:#f0f0f0;margin:0;padding:20px;display:flex;flex-direction:column;align-items:center;min-height:100vh;box-sizing:border-box}}.container{{width:100%;max-width:800px;background-color:#fff;border:1px solid #ccc;box-shadow:0 2px 5px rgba(0,0,0,0.1)}}.card-display{{min-height:200px;padding:20px;font-size:1.5em;text-align:center;border-bottom:1px solid #ccc;cursor:pointer}}.controls{{display:flex;justify-content:space-between;padding:10px;background-color:#f9f9f9}}button{{font-size:1.2em;padding:15px 20px;border:1px solid #ccc;background-color:#e9e9e9;cursor:pointer;flex-grow:1;margin:5px;border-radius:5px}}button:hover{{background-color:#ddd}}.counter{{text-align:center;padding:10px;font-size:1em;color:#555}}.card{{display:none}}.back{{display:none}}</style></head><body><div class="container"><div class="card-display" id="card-display" onclick="flipCard()">Toque para começar</div><div class="controls"><button onclick="prevCard()">Anterior</button><button onclick="nextCard()">Próximo</button></div><div class="counter" id="counter"></div></div><div id="card-data">{cards_html}</div><script>const cards=document.querySelectorAll('#card-data .card'),cardDisplay=document.getElementById('card-display'),counterDisplay=document.getElementById('counter');let currentCardIndex=0,isFront=!0;function showCard(e){{if(0===cards.length){{cardDisplay.innerHTML="Nenhum cartão encontrado.";counterDisplay.innerHTML="0 / 0";return}}currentCardIndex=e,isFront=!0;const t=cards[currentCardIndex].querySelector('.front').innerHTML;cardDisplay.innerHTML=t,counterDisplay.innerHTML=`${{currentCardIndex+1}} / ${{cards.length}}`}}function flipCard(){{if(0===cards.length)return;isFront=!isFront;const e=isFront?cards[currentCardIndex].querySelector('.front').innerHTML:cards[currentCardIndex].querySelector('.back').innerHTML;cardDisplay.innerHTML=e}}function nextCard(){{const e=(currentCardIndex+1)%cards.length;showCard(e)}}function prevCard(){{const e=(currentCardIndex-1+cards.length)%cards.length;showCard(e)}}showCard(0);</script></body></html>
    """
    os.makedirs("public", exist_ok=True)
    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(html_template)
    print("Ficheiro public/index.html criado com sucesso.")

if __name__ == "__main__":
    anki_download_and_process()


