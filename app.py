import json
import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# --- 설정 ---
CONFIG_FILE = 'config.json'
ADMIN_PASSWORD = "1234"  # 관리자 비밀번호 (원하는 대로 수정하세요)

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
        'Referer': url,
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8'
    }

def extract_keyword_from_url(url):
    """URL에서 검색어 파라미터를 추출합니다."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    # 구청마다 다른 검색 파라미터들 (sv, searchKrwd, searchKeyword, kwd 등)
    for p in ['sv', 'searchKrwd', 'searchKeyword', 'searchWrd', 'kwd']:
        if p in params:
            return params[p][0]
    return None

def parse_date(date_str):
    """문자열 날짜를 datetime 객체로 변환합니다."""
    if not date_str: return datetime(1900, 1, 1)
    try:
        clean_date = re.sub(r'[^0-9-]', '-', date_str.replace('.', '-')).strip('-')
        parts = clean_date.split('-')
        if len(parts[0]) == 2: parts[0] = '20' + parts[0] # YY-MM-DD 대응
        return datetime.strptime("-".join(parts[:3]), '%Y-%m-%d')
    except:
        return datetime(1900, 1, 1)

def scrape_board(url):
    posts = []
    # URL 자체에서 키워드 추출 (필터링용)
    url_keyword = extract_keyword_from_url(url)
    
    try:
        response = requests.get(url, headers=get_headers(url), verify=False, timeout=15)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 행 선택자 시도
        rows = soup.select('table tbody tr, .board-list tr, .bbs-list tr, .result-list li, .list_type li, .news-list li, .search-result-list li')
        
        for row in rows:
            title_elem = row.select_one('td.subject a, td.title a, td a, a.link, .title a, a')
            if not title_elem: continue
            
            title = title_elem.get_text(strip=True)
            if len(title) < 4: continue # 너무 짧은 제목 제외
            
            # 1. 키워드 필터링: URL에 키워드가 있는데 제목에 없으면 제외
            if url_keyword and url_keyword not in title:
                continue
            
            raw_link = title_elem.get('href', '')
            if not raw_link or raw_link.startswith('javascript'): continue
            full_link = urljoin(url, raw_link)
            
            # 날짜 찾기
            date_val = ""
            for de in row.select('td, span, .date, .reg-date'):
                txt = de.get_text(strip=True)
                if re.match(r'\d{2,4}[-./]\d{2}[-./]\d{2}', txt):
                    date_val = txt
                    break
            
            posts.append({
                'title': title, 
                'link': full_link, 
                'date': date_val,
                'dt_obj': parse_date(date_val)
            })
            
        # 2. 날짜순 정렬 (공지사항 무시하고 최신글이 위로 오게)
        posts.sort(key=lambda x: x['dt_obj'], reverse=True)
        
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        
    return posts[:15] # 게시판당 최대 15개

@app.route('/')
def index():
    config = load_config()
    return render_template('index.html', boards=config.get('boards', []))

@app.route('/api/scrape_all')
def api_scrape_all():
    config = load_config()
    all_results = []
    all_feed = []
    
    for board in config.get('boards', []):
        posts = scrape_board(board['url'])
        # dt_obj는 JSON 변환이 안되므로 문자열 처리 후 삭제
        for p in posts:
            p.pop('dt_obj', None)
            all_feed.append({**p, 'source': board['name']})
            
        all_results.append({
            'name': board['name'],
            'url': board['url'],
            'posts': posts
        })
    
    return jsonify({
        'success': True,
        'data': all_results,
        'latest_feed': all_feed,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/boards', methods=['POST', 'DELETE'])
def manage_boards():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'success': False, 'message': 'Password Denied'}), 403
    
    config = load_config()
    if request.method == 'POST':
        config['boards'].append({'name': data['name'], 'url': data['url']})
    elif request.method == 'DELETE':
        config['boards'] = [b for b in config['boards'] if b['url'] != data['url']]
    
    save_config(config)
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)