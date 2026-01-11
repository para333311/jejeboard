import json
import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from datetime import datetime
from urllib.parse import urljoin
import urllib3
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import pytz

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

CONFIG_FILE = 'config.json'
CACHE_FILE = 'cache.json'
VISITORS_FILE = 'visitors.json'
ADMIN_PASSWORD = "1111" # 기본 비밀번호

# 스케줄러 초기화
scheduler = BackgroundScheduler()
scheduler.start()

# 앱 종료 시 스케줄러도 종료
atexit.register(lambda: scheduler.shutdown())

def get_korean_time():
    """한국 시간(KST) 반환"""
    kst = pytz.timezone('Asia/Seoul')
    return datetime.now(kst)

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
        
        rows = soup.select('table tbody tr, .board-list tr, .bbs-list tr, .list_type li, .news-list li, .search-result-list li, .list-wrap li')
        if not rows:
            rows = soup.select('.title, .subject, .txt_left, .tit')

        for row in rows:
            title_elem = row.select_one('a, .tit, .subject, .title')
            if not title_elem: continue
            
            title = title_elem.get_text(strip=True)
            if len(title) < 3: continue
            
            # 키워드 필터링
            if keyword and keyword.strip():
                if keyword.strip() not in title:
                    continue
            
            link = title_elem.get('href', '')
            if not link or '#' in link or 'javascript' in link:
                parent_a = row.find_parent('a') or row.find('a')
                if parent_a: link = parent_a.get('href', '')

            full_link = urljoin(url, link)
            
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
                'dt_obj': parse_date(date_val),
                'source': name
            })
            
        posts.sort(key=lambda x: x['dt_obj'], reverse=True)
        
    except Exception as e:
        print(f"Error scraping {name}: {e}")
    
    return posts

def load_cache():
    """캐시 파일에서 데이터 로드"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return None

def save_cache(data):
    """캐시 파일에 데이터 저장"""
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_visitors():
    """방문자 데이터 로드"""
    if os.path.exists(VISITORS_FILE):
        try:
            with open(VISITORS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"today": 0, "total": 0, "date": get_korean_time().strftime('%Y-%m-%d')}

def save_visitors(data):
    """방문자 데이터 저장"""
    with open(VISITORS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def increment_visitor():
    """방문자 수 증가"""
    visitors = load_visitors()
    today = get_korean_time().strftime('%Y-%m-%d')

    # 날짜가 바뀌면 오늘 방문자 초기화
    if visitors.get('date') != today:
        visitors['today'] = 0
        visitors['date'] = today

    visitors['today'] += 1
    visitors['total'] += 1
    save_visitors(visitors)
    return visitors

def background_scrape():
    """백그라운드에서 크롤링 실행 (30분마다)"""
    print(f"[{get_korean_time().strftime('%Y-%m-%d %H:%M:%S')}] 백그라운드 크롤링 시작...")

    config = load_config()
    all_results = []
    integrated_feed = []

    for board in config.get('boards', []):
        kw = board.get('keyword', '')
        posts = scrape_board(board['url'], board['name'], kw)

        # 개별 게시판 결과 저장
        clean_posts = []
        for p in posts:
            integrated_feed.append(p.copy())
            p_copy = p.copy()
            p_copy.pop('dt_obj', None)
            clean_posts.append(p_copy)

        all_results.append({
            'name': board['name'],
            'url': board['url'],
            'keyword': kw,
            'posts': clean_posts[:15]
        })

    # 통합 피드 최신순 정렬
    integrated_feed.sort(key=lambda x: x['dt_obj'], reverse=True)
    for p in integrated_feed:
        p.pop('dt_obj', None)

    # 캐시에 저장
    cache_data = {
        'success': True,
        'data': all_results,
        'latest_posts': integrated_feed[:30],
        'updated_at': get_korean_time().strftime('%Y-%m-%d %H:%M:%S')
    }
    save_cache(cache_data)

    print(f"[{get_korean_time().strftime('%Y-%m-%d %H:%M:%S')}] 크롤링 완료! (게시판 {len(all_results)}개)")

@app.route('/')
def index():
    config = load_config()
    return render_template('index.html', boards=config.get('boards', []))

@app.route('/api/scrape_all')
def api_scrape_all():
    """캐시된 데이터 반환 (캐시 없으면 즉시 크롤링)"""
    cache = load_cache()

    if cache:
        return jsonify(cache)

    # 캐시 없으면 즉시 크롤링
    background_scrape()
    cache = load_cache()

    if cache:
        return jsonify(cache)

    # 그래도 없으면 빈 데이터 반환
    return jsonify({
        'success': True,
        'data': [],
        'latest_posts': [],
        'updated_at': get_korean_time().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/api/boards', methods=['POST', 'DELETE'])
def manage_boards():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'success': False, 'message': 'Password Denied'}), 403

    config = load_config()
    if request.method == 'POST':
        config['boards'].append({'name': data['name'], 'url': data['url'], 'keyword': data.get('keyword', '')})
    elif request.method == 'DELETE':
        config['boards'] = [b for b in config['boards'] if b['url'] != data['url']]
    save_config(config)
    return jsonify({'success': True})

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """즉시 크롤링 실행"""
    print("수동 새로고침 요청 받음")
    background_scrape()
    cache = load_cache()
    return jsonify(cache if cache else {'success': False, 'message': 'Refresh failed'})

@app.route('/api/visitors', methods=['GET', 'POST'])
def visitors():
    """방문자 수 관리"""
    if request.method == 'POST':
        # 방문자 카운트 증가
        visitors_data = increment_visitor()
        return jsonify(visitors_data)
    else:
        # 방문자 수 조회
        visitors_data = load_visitors()
        return jsonify(visitors_data)

if __name__ == '__main__':
    # 앱 시작 시 즉시 한 번 크롤링
    print("앱 시작! 초기 크롤링 실행 중...")
    background_scrape()

    # 30분마다 크롤링 스케줄 등록
    scheduler.add_job(
        func=background_scrape,
        trigger="interval",
        minutes=30,
        id='scrape_job',
        name='30분마다 게시판 크롤링',
        replace_existing=True
    )
    print("스케줄러 등록 완료! 30분마다 크롤링합니다.")

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)