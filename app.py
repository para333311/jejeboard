import json
import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from datetime import datetime
from urllib.parse import urljoin
import urllib3
import asyncio
import threading
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()  # .env 파일 로드

app = Flask(__name__)

CONFIG_FILE = 'config.json'
ADMIN_PASSWORD = "1111" # 기본 비밀번호

# 텔레그램 봇 설정
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_ENABLED = TELEGRAM_BOT_TOKEN is not None
telegram_bot = None
previous_posts = set()  # 이전에 확인한 게시물 추적 (title, link 튜플)

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

@app.route('/')
def index():
    config = load_config()
    return render_template('index.html', boards=config.get('boards', []))

def scrape_all_boards():
    """모든 게시판 크롤링 (내부 함수)"""
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

    # dt_obj 제거 (JSON 직렬화용)
    latest_posts = []
    for p in integrated_feed[:30]:
        p_copy = p.copy()
        p_copy.pop('dt_obj', None)
        latest_posts.append(p_copy)

    return {
        'success': True,
        'data': all_results,
        'latest_posts': latest_posts,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

@app.route('/api/scrape_all')
def api_scrape_all():
    """API 엔드포인트: 모든 게시판 크롤링"""
    return jsonify(scrape_all_boards())

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

async def check_new_posts():
    """새 게시물 체크 및 알림 전송"""
    global previous_posts, telegram_bot

    if not telegram_bot:
        return

    try:
        result = scrape_all_boards()
        latest_posts = result.get('latest_posts', [])

        new_posts = []
        for post in latest_posts[:5]:  # 최신 5개만 체크
            post_id = (post['title'], post['link'])
            if post_id not in previous_posts:
                new_posts.append(post)
                previous_posts.add(post_id)

        # 너무 많은 게시물이 쌓이지 않도록 제한
        if len(previous_posts) > 1000:
            previous_posts = set(list(previous_posts)[-500:])

        # 새 게시물 알림
        if new_posts:
            for post in new_posts:
                message = (
                    f"🆕 *새 게시물 알림*\n\n"
                    f"*{post['title']}*\n"
                    f"출처: {post['source']}\n"
                )
                if post.get('date'):
                    message += f"날짜: {post['date']}\n"
                message += f"\n{post['link']}"

                await telegram_bot.send_notification(message)

    except Exception as e:
        print(f"Error checking new posts: {e}")

async def monitor_posts():
    """백그라운드에서 주기적으로 게시물 모니터링"""
    global previous_posts

    # 초기 게시물 로드 (알림 방지)
    try:
        result = scrape_all_boards()
        for post in result.get('latest_posts', [])[:20]:
            previous_posts.add((post['title'], post['link']))
    except Exception as e:
        print(f"Error loading initial posts: {e}")

    # 주기적 체크 (5분마다)
    while True:
        await asyncio.sleep(300)  # 5분
        await check_new_posts()

def run_telegram_bot():
    """텔레그램 봇을 별도 스레드에서 실행"""
    global telegram_bot

    if not TELEGRAM_ENABLED:
        print("Telegram bot disabled (TELEGRAM_BOT_TOKEN not set)")
        return

    try:
        from telegram_bot import create_bot

        telegram_bot = create_bot(TELEGRAM_BOT_TOKEN, scrape_all_boards)

        # 비동기 이벤트 루프 생성
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 봇 초기화 및 모니터링 시작
        loop.run_until_complete(telegram_bot.initialize())
        loop.create_task(monitor_posts())
        loop.run_forever()

    except Exception as e:
        print(f"Error running telegram bot: {e}")

if __name__ == '__main__':
    # 텔레그램 봇을 백그라운드 스레드에서 시작
    if TELEGRAM_ENABLED:
        bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
        bot_thread.start()
        print("Telegram bot started in background")
    else:
        print("Telegram bot disabled")

    # Flask 앱 시작
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)