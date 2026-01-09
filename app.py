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
ADMIN_PASSWORD = "1234" # 관리자 비밀번호

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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': url
    }

def parse_date(date_str):
    if not date_str: return datetime(1900, 1, 1)
    try:
        clean_date = re.sub(r'[^0-9-]', '-', date_str.replace('.', '-')).strip('-')
        parts = clean_date.split('-')
        if len(parts[0]) == 2: parts[0] = '20' + parts[0]
        return datetime.strptime("-".join(parts[:3]), '%Y-%m-%d')
    except:
        return datetime(1900, 1, 1)

def scrape_board(url, name, keyword):
    posts = []
    try:
        session = requests.Session()
        response = session.get(url, headers=get_headers(url), verify=False, timeout=15)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 게시판 공통 패턴 탐색
        rows = soup.select('table tbody tr, .board-list tr, .bbs-list tr, .list_type li, .news-list li, .search-result-list li, .list-wrap li')
        
        if not rows: # 특수 구조 대응
            rows = soup.select('.title, .subject, .txt_left, .tit')

        for row in rows:
            title_elem = row.select_one('a, .tit, .subject, .title')
            if not title_elem: continue
            
            title = title_elem.get_text(strip=True)
            if len(title) < 3: continue
            
            # [핵심] 키워드 필터링 로직
            # 키워드가 설정되어 있다면 제목에 포함된 경우만 가져옴
            if keyword and keyword.strip():
                if keyword.strip() not in title:
                    continue
            
            link = title_elem.get('href', '')
            if not link or '#' in link or 'javascript' in link:
                parent_a = row.find_parent('a') or row.find('a')
                if parent_a: link = parent_a.get('href', '')

            full_link = urljoin(url, link)
            
            # 날짜 찾기
            date_val = ""
            for elem in row.select('td, span, .date, .reg_date, .day'):
                txt = elem.get_text(strip=True)
                if re.search(r'\d{2,4}[-./]\d{1,2}[-./]\d{1,2}', txt):
                    date_val = txt
                    break
            
            posts.append({
                'title': title,
                'link': full_link,
                'date': date_val,
                'dt_obj': parse_date(date_val)
            })
            
        # 날짜 최신순 정렬
        posts.sort(key=lambda x: x['dt_obj'], reverse=True)
        
    except Exception as e:
        print(f"Error scraping {name}: {e}")
    
    return posts[:15]

@app.route('/')
def index():
    config = load_config()
    return render_template('index.html', boards=config.get('boards', []))

@app.route('/api/scrape_all')
def api_scrape_all():
    config = load_config()
    all_results = []
    
    for board in config.get('boards', []):
        # keyword 항목이 없으면 빈 문자열로 처리 (호환성)
        kw = board.get('keyword', '')
        posts = scrape_board(board['url'], board['name'], kw)
        
        for p in posts: p.pop('dt_obj', None)
        
        all_results.append({
            'name': board['name'],
            'url': board['url'],
            'keyword': kw,
            'posts': posts
        })
    
    return jsonify({
        'success': True,
        'data': all_results,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/boards', methods=['POST', 'DELETE'])
def manage_boards():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'success': False, 'message': 'Password Denied'}), 403
    
    config = load_config()
    if request.method == 'POST':
        config['boards'].append({
            'name': data['name'], 
            'url': data['url'], 
            'keyword': data.get('keyword', '') # 키워드 저장 추가
        })
    elif request.method == 'DELETE':
        config['boards'] = [b for b in config['boards'] if b['url'] != data['url']]
    
    save_config(config)
    return jsonify({'success': True})

if __name__ == '__main__':
    # 초기 주소 자동 세팅
    if not os.path.exists(CONFIG_FILE) or len(load_config()['boards']) == 0:
        default_boards = [
            {"name": "강남구 재건축", "url": "https://www.gangnam.go.kr/board/union6/list.do?mid=ID02_01130505", "keyword": ""},
            {"name": "마포구 신속통합", "url": "https://www.mapo.go.kr/site/main/board/notice/list", "keyword": "신속통합"},
            {"name": "서울시 보도자료", "url": "https://www.seoul.go.kr/news/news_report.do", "keyword": "재개발"},
            {"name": "서울시보", "url": "https://event.seoul.go.kr/seoulsibo/list.do", "keyword": ""}
        ]
        save_config({"boards": default_boards})
    
    app.run(host='0.0.0.0', port=5000, debug=True)