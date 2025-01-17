from flask import Flask, render_template, request
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

app = Flask(__name__)
concursos_cache = []
cache_lock = Lock()
last_update = 0
CACHE_DURATION = 300  # 5 minutos em segundos

def scrape_concursos(url, status):
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(options=options)
    lista_concursos = []
    
    try:
        driver.get(url)
        time.sleep(3)
        
        cards = driver.find_elements(By.CSS_SELECTOR, '.q_circle_outer')
        
        for card in cards:
            try:
                titulo = card.find_element(By.TAG_NAME, 'h3').text.strip()
                info_texto = card.find_element(By.CLASS_NAME, 'q_circle_text_holder').text.strip()
                vagas = ''
                salario = ''
                
                linhas = info_texto.split('\n')
                for linha in linhas:
                    if 'vagas' in linha.lower():
                        vagas = linha.strip()
                    elif 'r$' in linha.lower():
                        salario = linha.strip()
                
                link = card.find_element(By.CLASS_NAME, 'icon_with_title_link').get_attribute('href')
                
                # Extrai apenas números
                num_vagas = int(''.join(filter(str.isdigit, vagas))) if vagas else 0
                valor_salario = float(''.join(filter(str.isdigit, salario)).replace(',', '.')) if salario else 0
                
                concurso = {
                    'titulo': titulo,
                    'vagas': vagas,
                    'salario': salario,
                    'link': link,
                    'status': status,
                    'num_vagas': num_vagas,
                    'valor_salario': valor_salario
                }
                
                lista_concursos.append(concurso)
                
            except Exception as e:
                print(f"Erro ao processar card: {str(e)}")
                continue
                
    except Exception as e:
        print(f"Erro ao buscar elementos: {str(e)}")
    finally:
        driver.quit()
        
    return lista_concursos

def atualizar_cache():
    global concursos_cache, last_update
    
    urls = {
        'Novos': 'https://cebraspe.org.br/concursos/Novos',
        'Inscrições Abertas': 'https://www.cebraspe.org.br/concursos/inscricoes-abertas/',
        'Em Andamento': 'https://www.cebraspe.org.br/concursos/em-andamento'
    }
    
    with ThreadPoolExecutor(max_workers=len(urls)) as executor:
        future_to_status = {
            executor.submit(scrape_concursos, url, status): status
            for status, url in urls.items()
        }
        
        todos_concursos = []
        for future in as_completed(future_to_status):
            try:
                concursos = future.result()
                todos_concursos.extend(concursos)
            except Exception as e:
                print(f"Erro ao processar URL: {str(e)}")
    
    with cache_lock:
        concursos_cache = todos_concursos
        last_update = time.time()

def get_float_value(value, default=0):
    if not value:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def get_int_value(value, default=0):
    if not value:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

@app.route('/')
def index():
    global last_update, concursos_cache
    
    # Atualiza o cache se necessário
    if time.time() - last_update > CACHE_DURATION:
        atualizar_cache()
    
    # Se o cache estiver vazio (primeira execução), atualiza
    if not concursos_cache:
        atualizar_cache()
    
    # Obtém os filtros
    status_filter = request.args.get('status', '')
    min_salario = get_float_value(request.args.get('min_salario'))
    max_salario = get_float_value(request.args.get('max_salario', ''), sys.float_info.max)
    min_vagas = get_int_value(request.args.get('min_vagas'))
    max_vagas = get_int_value(request.args.get('max_vagas', ''), sys.maxsize)
    
    # Aplica os filtros
    concursos_filtrados = concursos_cache
    if status_filter:
        concursos_filtrados = [c for c in concursos_filtrados if c['status'] == status_filter]
    concursos_filtrados = [c for c in concursos_filtrados if min_salario <= c['valor_salario'] <= max_salario]
    concursos_filtrados = [c for c in concursos_filtrados if min_vagas <= c['num_vagas'] <= max_vagas]
    
    # Lista única de status para o filtro
    status_options = sorted(list(set(c['status'] for c in concursos_cache)))
    
    return render_template('index.html', 
                         concursos=concursos_filtrados,
                         status_options=status_options,
                         current_status=status_filter,
                         min_salario=min_salario if min_salario > 0 else '',
                         max_salario=max_salario if max_salario != sys.float_info.max else '',
                         min_vagas=min_vagas if min_vagas > 0 else '',
                         max_vagas=max_vagas if max_vagas != sys.maxsize else '')

if __name__ == '__main__':
    app.run(debug=True)
