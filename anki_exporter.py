import os
import requests
import zipfile
import json
from bs4 import BeautifulSoup

def anki_download_with_cookie():
    """
    Faz o download da coleção de baralhos do AnkiWeb usando um cookie de sessão.
    Este método é mais robusto pois simula o processo de um navegador.
    """
    cookie_value = os.environ.get("ANKIWEB_SESSION_COOKIE")
    if not cookie_value:
        raise Exception("O 'Secret' ANKIWEB_SESSION_COOKIE não foi configurado no GitHub.")

    with requests.Session() as session:
        # Define o cookie na sessão para autenticação
        session.cookies.set("ankiweb", cookie_value)
        
        # Define cabeçalhos para simular um navegador real
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://ankiweb.net/decks/",
        }
        session.headers.update(headers)

        # 1. Visitar a página de baralhos para obter o CSRF token
        print("A visitar a página de baralhos para obter o token de segurança...")
        try:
            decks_page_response = session.get("https://ankiweb.net/decks/")
            decks_page_response.raise_for_status() # Lança um erro se a página não carregar
        except requests.exceptions.RequestException as e:
            print(f"--- DEBUG INFO ---")
            print(f"Erro ao aceder à página de baralhos: {e}")
            raise Exception("Não foi possível carregar a página de baralhos do AnkiWeb. O cookie pode ser inválido.")

        # 2. Extrair o CSRF token do HTML da página
        soup = BeautifulSoup(decks_page_response.text, 'html.parser')
        csrf_token_element = soup.find('input', {'name': 'csrf_token'})
        
        if not csrf_token_element:
            print("--- DEBUG INFO ---")
            print("Não foi encontrado nenhum 'csrf_token' na página de baralhos.")
            print("A resposta da página foi:", decks_page_response.text[:500])
            raise Exception("Não foi possível encontrar o token de segurança (CSRF) na página de baralhos.")
            
        csrf_token = csrf_token_element.get('value')
        print("Token de segurança (CSRF) extraído com sucesso.")

        # 3. Fazer o pedido de exportação com o CSRF token
        print("A fazer o pedido de exportação da coleção...")
        export_url = "https://ankiweb.net/decks/export/apkg"
        export_data = {
            "csrf_token": csrf_token
        }
        
        try:
            download_response = session.post(export_url, data=export_data)
            download_response.raise_for_status() # Lança erro se o status não for 200
        except requests.exceptions.RequestException as e:
            print(f"--- DEBUG INFO ---")
            print(f"Status Code: {e.response.status_code if e.response else 'N/A'}")
            print(f"URL: {export_url}")
            print(f"Response Text (início): {e.response.text[:500] if e.response else 'N/A'}")
            raise Exception("Não foi possível baixar a coleção. O cookie pode ser inválido ou ter expirado.")


        # Salva o conteúdo do baralho num ficheiro .apkg
        with open("collection.apkg", "wb") as f:
            f.write(download_response.content)
        print("Coleção de baralhos (.apkg) baixada com sucesso.")


def process_deck():
    # Esta função permanece a mesma
    deck_name_to_find = os.environ.get("DECK_NAME")
    if not deck_name_to_find:
        raise Exception("O 'Secret' DECK_NAME não foi configurado no GitHub.")

    print(f"A processar o ficheiro .apkg para encontrar o baralho: '{deck_name_to_find}'")
    with zipfile.ZipFile("collection.apkg", "r") as z:
        collection_data = json.loads(z.read("collection.anki21"))
        media_data = json.loads(z.read("media"))

        decks = {d['id']: d['name'] for d in collection_data['decks']}
        models = {m['id']: m for m in collection_data['models']}
        
        target_deck_id = None
        for did, name in decks.items():
            if name == deck_name_to_find:
                target_deck_id = did
                break
        
        if not target_deck_id:
            available_decks = list(decks.values())
            raise Exception(f"Baralho '{deck_name_to_find}' não encontrado. Baralhos disponíveis: {available_decks}")

        print(f"Baralho encontrado. ID: {target_deck_id}. A extrair cartões...")
        cards_html = ""
        notes = [note for note in collection_data['notes'] if note['did'] == target_deck_id]

        for note in notes:
            model = models[note['mid']]
            fields = model['flds']
            field_values = note['flds']
            
            front_field_name = fields[0]['name']
            back_field_name = fields[1]['name'] if len(fields) > 1 else fields[0]['name']
            
            front_content = field_values[0]
            back_content = field_values[1] if len(field_values) > 1 else field_values[0]

            cards_html += f"""
            <div class="card">
                <div class="front">{front_content}</div>
                <div class="back">{back_content}</div>
            </div>
            """
        
        return cards_html

def create_html_file(cards_html):
    # Esta função permanece a mesma
    html_template = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Anki Viewer</title>
        <style>
            body {{ font-family: sans-serif; background-color: #f0f0f0; margin: 0; padding: 20px; display: flex; flex-direction: column; align-items: center; min-height: 100vh; box-sizing: border-box; }}
            .container {{ width: 100%; max-width: 800px; background-color: #fff; border: 1px solid #ccc; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            .card-display {{ min-height: 200px; padding: 20px; font-size: 1.5em; text-align: center; border-bottom: 1px solid #ccc; cursor: pointer; }}
            .controls {{ display: flex; justify-content: space-between; padding: 10px; background-color: #f9f9f9; }}
            button {{ font-size: 1.2em; padding: 15px 20px; border: 1px solid #ccc; background-color: #e9e9e9; cursor: pointer; flex-grow: 1; margin: 5px; border-radius: 5px; }}
            button:hover {{ background-color: #ddd; }}
            .counter {{ text-align: center; padding: 10px; font-size: 1em; color: #555; }}
            .card {{ display: none; }}
            .back {{ display: none; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card-display" id="card-display" onclick="flipCard()">Toque para começar</div>
            <div class="controls">
                <button onclick="prevCard()">Anterior</button>
                <button onclick="nextCard()">Próximo</button>
            </div>
            <div class="counter" id="counter"></div>
        </div>

        <div id="card-data">
            {cards_html}
        </div>

        <script>
            const cards = document.querySelectorAll('#card-data .card');
            const cardDisplay = document.getElementById('card-display');
            const counterDisplay = document.getElementById('counter');
            let currentCardIndex = 0;
            let isFront = true;

            function showCard(index) {{
                if (cards.length === 0) {{
                    cardDisplay.innerHTML = "Nenhum cartão encontrado.";
                    counterDisplay.innerHTML = "0 / 0";
                    return;
                }}
                currentCardIndex = index;
                isFront = true;
                const frontContent = cards[currentCardIndex].querySelector('.front').innerHTML;
                cardDisplay.innerHTML = frontContent;
                counterDisplay.innerHTML = `${{currentCardIndex + 1}} / ${{cards.length}}`;
            }}

            function flipCard() {{
                if (cards.length === 0) return;
                isFront = !isFront;
                const content = isFront ? cards[currentCardIndex].querySelector('.front').innerHTML : cards[currentCardIndex].querySelector('.back').innerHTML;
                cardDisplay.innerHTML = content;
            }}

            function nextCard() {{
                const newIndex = (currentCardIndex + 1) % cards.length;
                showCard(newIndex);
            }}

            function prevCard() {{
                const newIndex = (currentCardIndex - 1 + cards.length) % cards.length;
                showCard(newIndex);
            }}
            
            showCard(0); // Mostra o primeiro cartão ao carregar
        </script>
    </body>
    </html>
    """
    os.makedirs("public", exist_ok=True)
    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(html_template)
    print("Ficheiro public/index.html criado com sucesso.")

if __name__ == "__main__":
    anki_download_with_cookie()
    cards_content = process_deck()
    create_html_file(cards_content)



