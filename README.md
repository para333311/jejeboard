# 제주 게시판 통합 크롤러

여러 게시판을 실시간으로 모니터링하고 텔레그램으로 알림을 받는 서비스입니다.

## 주요 기능

- 🔍 여러 게시판 동시 크롤링
- 🎯 키워드 필터링
- 📱 텔레그램 봇 알림
- 📊 통합 피드 제공
- 🌐 웹 인터페이스

## 설치 방법

1. 저장소 클론
```bash
git clone <repository-url>
cd jejeboard
```

2. 의존성 설치
```bash
pip install -r requirements.txt
```

3. 환경변수 설정
```bash
cp .env.example .env
# .env 파일을 열어 텔레그램 봇 토큰 입력
```

## 텔레그램 봇 설정

### 1. 봇 생성

1. 텔레그램에서 [@BotFather](https://t.me/botfather) 검색
2. `/newbot` 명령어 입력
3. 봇 이름과 사용자명 설정
4. 받은 토큰을 `.env` 파일에 입력

### 2. 환경변수 설정

`.env` 파일:
```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

### 3. 봇 사용법

텔레그램에서 봇을 검색하여 대화를 시작하세요.

#### 명령어

- `/start` - 봇 시작 및 알림 구독
- `/latest` - 최신 게시물 Top 10 조회
- `/boards` - 등록된 게시판 목록
- `/stop` - 알림 구독 중지
- `/help` - 도움말

## 실행

```bash
python app.py
```

웹 인터페이스: http://localhost:5000

## 게시판 추가

웹 인터페이스에서:
1. 관리자 비밀번호 입력 (기본: 1111)
2. 게시판 이름, URL, 키워드 입력
3. "추가" 버튼 클릭

## 배포

### Render

1. Render 대시보드에서 새 웹 서비스 생성
2. 저장소 연결
3. 환경변수 설정:
   - `TELEGRAM_BOT_TOKEN`: 텔레그램 봇 토큰
4. 배포

## 기술 스택

- **Backend**: Python Flask
- **Scraping**: BeautifulSoup4, Requests
- **Bot**: python-telegram-bot
- **Deployment**: Gunicorn

## 라이선스

MIT License
