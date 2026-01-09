import json
import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from datetime import datetime
from urllib.parse import urljoin
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

CONFIG_FILE = 'config.json'
ADMIN_PASSWORD = "1111"  # 여기서 비밀번호를 수정하세요!

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"boards": []}

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def get_headers(url):
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': url
    }

def scrape_board(url):
    posts = []
    try:
        response = requests.get(url, headers=get_headers(url), verify=False, timeout=15)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.select('table tbody tr, .board-list tr, .bbs-list tr, .result-list li, .list_type li, .news-list li')
        
        for row in rows[:15]:
            title_elem = row.select_one('td.subject a, td.title a, td a, a.link, a')
            if not title_elem or len(title_elem.get_text(strip=True)) < 3: continue
            
            title = title_elem.get_text(strip=True)
            raw_link = title_elem.get('href', '')
            full_link = urljoin(url, raw_link) # 링크 자동 복구 기능
            
            date = ""
            date_elems = row.select('td, span, .date')
            for de in date_elems:
                txt = de.get_text(strip=True)
                if re.match(r'\d{4}[-./]\d{2}[-./]\d{2}', txt):
                    date = txt
                    break
            posts.append({'title': title, 'link': full_link, 'date': date})
    except: pass
    return posts

@app.route('/')
def index():
    config = load_config()
    return render_template('index.html', boards=config.get('boards', []))

@app.route('/api/scrape_all')
def api_scrape_all():
    config = load_config()
    all_results = []
    for board in config.get('boards', []):
        posts = scrape_board(board['url'])
        all_results.append({'name': board['name'], 'url': board['url'], 'posts': posts})
    return jsonify({'success': True, 'data': all_results, 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})

@app.route('/api/boards', methods=['POST', 'DELETE'])
def manage_boards():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'success': False, 'message': '비밀번호가 틀렸습니다.'}), 403
    config = load_config()
    if request.method == 'POST':
        config['boards'].append({'name': data['name'], 'url': data['url']})
    elif request.method == 'DELETE':
        config['boards'] = [b for b in config['boards'] if b['url'] != data['url']]
    save_config(config)
    return jsonify({'success': True})

if __name__ == '__main__':
    if not os.path.exists(CONFIG_FILE):
        save_config({"boards": [
            {"name": "강남구 재건축", "url": "https://www.gangnam.go.kr/board/union6/list.do?mid=ID02_01130505"},
            {"name": "마포구 신속통합", "url": "https://www.mapo.go.kr/site/main/board/notice/list?baCommSelec=false&sc=&sv=%EC%8B%A0%EC%86%8D%ED%86%B5%ED%95%A9&pageSize=10"},
            {"name": "서울시보", "url": "https://event.seoul.go.kr/seoulsibo/list.do"}
        ]})
    app.run(host='0.0.0.0', port=5000)