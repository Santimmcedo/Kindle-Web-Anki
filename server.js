const http = require('http');
const https = require('https');
const url = require('url');

// A URL do seu túnel Pinggy será lida a partir das variáveis de ambiente do Render
const ankiConnectUrl = process.env.ANKICONNECT_URL;
const DECK_NAME = process.env.DECK_NAME;

if (!ankiConnectUrl || !DECK_NAME) {
    console.error("ERRO: As variáveis de ambiente ANKICONNECT_URL e DECK_NAME precisam de ser configuradas no Render.");
}

// --- MELHORIA: Agente com Keep-Alive para reutilizar a ligação ---
const agentOptions = {
    keepAlive: true,
    maxSockets: 1, // Como os pedidos são sequenciais, 1 socket é suficiente
    timeout: 45000 // Aumenta o timeout geral do agente
};
const httpAgent = new http.Agent(agentOptions);
const httpsAgent = new https.Agent(agentOptions);


// Função para fazer um pedido ao AnkiConnect, agora com lógica de "tentar novamente"
function ankiConnectRequest(action, params = {}, retries = 3) {
    return new Promise((resolve, reject) => {
        
        const attempt = (retryCount) => {
            const body = JSON.stringify({ action, version: 6, params });
            const isHttps = ankiConnectUrl.startsWith('https');
            
            const options = {
                hostname: url.parse(ankiConnectUrl).hostname,
                port: url.parse(ankiConnectUrl).port || (isHttps ? 443 : 80),
                path: '/',
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': body.length
                },
                agent: isHttps ? httpsAgent : httpAgent, // Usa o agente Keep-Alive
                timeout: 30000 // Timeout por pedido
            };

            const protocol = isHttps ? https : http;

            const req = protocol.request(options, (res) => {
                let data = '';
                res.on('data', (chunk) => { data += chunk; });
                res.on('end', () => {
                    try {
                        const parsed = JSON.parse(data);
                        if (parsed.error) {
                            reject(new Error(parsed.error));
                        } else {
                            resolve(parsed.result);
                        }
                    } catch (e) {
                        reject(new Error(`Falha ao analisar a resposta do AnkiConnect: ${data}`));
                    }
                });
            });
            
            req.on('timeout', () => {
                req.destroy();
                if (retryCount > 0) {
                    console.warn(`Tentativa ${4 - retryCount} falhou (timeout). A tentar novamente...`);
                    setTimeout(() => attempt(retryCount - 1), 1000); // Espera 1s antes de tentar de novo
                } else {
                    reject(new Error('A ligação ao AnkiConnect demorou demasiado tempo (timeout) após várias tentativas.'));
                }
            });

            req.on('error', (e) => {
                // --- MELHORIA: Lógica de "Tentar Novamente" ---
                const retryableErrors = ['ECONNRESET', 'EPIPE', 'ETIMEDOUT', 'SOCKET_HANG_UP'];
                if (retryCount > 0 && retryableErrors.some(errCode => e.message.includes(errCode))) {
                    console.warn(`Tentativa ${4 - retryCount} falhou (${e.message}). A tentar novamente...`);
                    setTimeout(() => attempt(retryCount - 1), 1000);
                } else {
                    reject(new Error(`Erro na ligação ao AnkiConnect: ${e.message}`));
                }
            });
            
            req.write(body);
            req.end();
        };

        attempt(retries); // Inicia a primeira tentativa
    });
}

// O nosso servidor web que o Kindle irá aceder
const server = http.createServer(async (req, res) => {
    if (!ankiConnectUrl || !DECK_NAME) {
        res.writeHead(500, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end("<h1>Erro de Configuração no Servidor</h1><p>As variáveis de ambiente não foram definidas corretamente no Render.</p>");
        return;
    }

    try {
        console.log(`A procurar por cartões no baralho: ${DECK_NAME}`);
        const cardIds = await ankiConnectRequest('findCards', { query: `deck:"${DECK_NAME}"` });
        
        if (cardIds.length === 0) {
             res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
             res.end(`<h1>Baralho Vazio</h1><p>Nenhum cartão foi encontrado no baralho "${DECK_NAME}".</p>`);
             return;
        }

        console.log(`Encontrados ${cardIds.length} cartões. A obter a informação em lotes...`);
        
        const batchSize = 20; 
        let allCardsInfo = [];
        const totalBatches = Math.ceil(cardIds.length / batchSize);

        for (let i = 0; i < cardIds.length; i += batchSize) {
            const batch = cardIds.slice(i, i + batchSize);
            const currentBatchNum = Math.floor(i / batchSize) + 1;
            console.log(`A processar lote ${currentBatchNum} de ${totalBatches}...`);
            const batchInfo = await ankiConnectRequest('cardsInfo', { cards: batch });
            allCardsInfo = allCardsInfo.concat(batchInfo);
        }
        
        console.log("Todos os lotes foram processados com sucesso!");
        let cardsHtml = "";
        for (const card of allCardsInfo) {
            const front_content = card.fields.Front ? card.fields.Front.value : "[Frente em branco]";
            const back_content = card.fields.Back ? card.fields.Back.value : "[Verso em branco]";
            cardsHtml += `
            <div class="card">
                <div class="front">${front_content}</div>
                <div class="back">${back_content}</div>
            </div>`;
        }
        
        const html_template = `
        <!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Anki Viewer</title><style>body{font-family:sans-serif;background-color:#f0f0f0;margin:0;padding:20px;display:flex;flex-direction:column;align-items:center;min-height:100vh;box-sizing:border-box}.container{width:100%;max-width:800px;background-color:#fff;border:1px solid #ccc;box-shadow:0 2px 5px rgba(0,0,0,0.1)}.card-display{min-height:200px;padding:20px;font-size:1.5em;text-align:center;border-bottom:1px solid #ccc;cursor:pointer}.controls{display:flex;justify-content:space-between;padding:10px;background-color:#f9f9f9}button{font-size:1.2em;padding:15px 20px;border:1px solid #ccc;background-color:#e9e9e9;cursor:pointer;flex-grow:1;margin:5px;border-radius:5px}button:hover{background-color:#ddd}.counter{text-align:center;padding:10px;font-size:1em;color:#555}.card{display:none}.back{display:none}}</style></head><body><div class="container"><div class="card-display" id="card-display" onclick="flipCard()">Toque para começar</div><div class="controls"><button onclick="prevCard()">Anterior</button><button onclick="nextCard()">Próximo</button></div><div class="counter" id="counter"></div></div><div id="card-data">${cardsHtml}</div><script>const cards=document.querySelectorAll('#card-data .card'),cardDisplay=document.getElementById('card-display'),counterDisplay=document.getElementById('counter');let currentCardIndex=0,isFront=!0;function showCard(e){if(0===cards.length){cardDisplay.innerHTML="Nenhum cartão encontrado.";counterDisplay.innerHTML="0 / 0";return}currentCardIndex=e,isFront=!0;const t=cards[currentCardIndex].querySelector('.front').innerHTML;cardDisplay.innerHTML=t,counterDisplay.innerHTML=\`\${currentCardIndex+1} / \${cards.length}\`}function flipCard(){if(0===cards.length)return;isFront=!isFront;const e=isFront?cards[currentCardIndex].querySelector('.front').innerHTML:cards[currentCardIndex].querySelector('.back').innerHTML;cardDisplay.innerHTML=e}function nextCard(){const e=(currentCardIndex+1)%cards.length;showCard(e)}function prevCard(){const e=(currentCardIndex-1+cards.length)%cards.length;showCard(e)}showCard(0);</script></body></html>`;

        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(html_template);

    } catch (error) {
        console.error("Erro ao processar o pedido:", error);
        res.writeHead(500, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(`<h1>Erro no Servidor</h1><p>Não foi possível comunicar com o seu AnkiConnect. Verifique se o Anki, o AnkiConnect e o seu túnel (Pinggy) estão a funcionar corretamente.</p><p><small>Detalhe do erro: ${error.message}</small></p>`);
    }
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log(`Servidor "ponte" a funcionar na porta ${PORT}`);
});

