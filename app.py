import os
import time
import hashlib
import hmac
import base64
import requests
import pandas as pd
from flask import Flask, request, render_template_string, send_file, session
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===============================
# 환경변수
# ===============================
ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")
CUSTOMER_ID = os.environ.get("CUSTOMER_ID")

BASE_URL = "https://api.searchad.naver.com"

app = Flask(__name__)
app.secret_key = "bookvpro_secure_key"

# ===============================
# 간단 캐시 (메모리 캐시)
# ===============================
cache = {}

# ===============================
# 서명 생성
# ===============================
def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    signature = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).digest()
    return base64.b64encode(signature).decode()

# ===============================
# 검색 함수
# ===============================
def search_keyword(keyword):

    keyword = keyword.strip()
    if not keyword:
        return None

    # 캐시 확인
    if keyword in cache:
        return cache[keyword]

    uri = "/keywordstool"
    method = "GET"
    timestamp = str(int(time.time() * 1000))

    signature = generate_signature(timestamp, method, uri, SECRET_KEY)

    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": ACCESS_KEY,
        "X-Customer": CUSTOMER_ID,
        "X-Signature": signature,
    }

    params = {
        "hintKeywords": keyword,
        "showDetail": 1
    }

    try:
        response = requests.get(
            BASE_URL + uri,
            headers=headers,
            params=params,
            timeout=7
        )

        if response.status_code != 200:
            return {
                "keyword": keyword,
                "pc": 0,
                "mobile": 0,
                "total": 0
            }

        data = response.json().get("keywordList", [])

        # 원본 키워드 정확 매칭
        target = None
        for item in data:
            if item["relKeyword"].replace(" ", "") == keyword.replace(" ", ""):
                target = item
                break

        if not target:
            return {
                "keyword": keyword,
                "pc": 0,
                "mobile": 0,
                "total": 0
            }

        pc_raw = target["monthlyPcQcCnt"]
        mobile_raw = target["monthlyMobileQcCnt"]

        def safe_convert(value):
            if isinstance(value, str):
                if "<" in value:
                    return 0
                return int(value.replace(",", ""))
            return int(value)

        pc = safe_convert(pc_raw)
        mobile = safe_convert(mobile_raw)

        result = {
            "keyword": keyword,
            "pc": pc,
            "mobile": mobile,
            "total": pc + mobile
        }

        cache[keyword] = result
        return result

    except Exception:
        return {
            "keyword": keyword,
            "pc": 0,
            "mobile": 0,
            "total": 0
        }

# ===============================
# 메인 페이지
# ===============================
@app.route("/")
def home():
    return render_template_string("""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>BookVPro</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
body { background:#f5f7fa; }
.container { max-width:900px; }
textarea { resize:none; }
</style>
</head>
<body>
<div class="container mt-5">
<h2 class="mb-4 text-center">📚 BookVPro 검색 시스템</h2>
<form method="POST" action="/search" onsubmit="showLoading()">
<textarea name="books" class="form-control mb-3" rows="10"
placeholder="책 제목을 한 줄에 하나씩 입력하세요 (최대 1000개)"></textarea>
<button class="btn btn-primary w-100">검색 시작</button>
</form>
<div id="loading" class="text-center mt-3" style="display:none;">
<div class="spinner-border text-primary"></div>
<p>검색 중입니다...</p>
</div>
</div>
<script>
function showLoading(){
document.getElementById("loading").style.display="block";
}
</script>
</body>
</html>
""")

# ===============================
# 병렬 검색 (순서 유지)
# ===============================
@app.route("/search", methods=["POST"])
def search():
    books = request.form.get("books", "")
    books = [b.strip() for b in books.split("\\n") if b.strip()]

    results = [None] * len(books)

    with ThreadPoolExecutor(max_workers=6) as executor:
        future_map = {
            executor.submit(search_keyword, books[i]): i
            for i in range(len(books))
        }

        for future in as_completed(future_map):
            index = future_map[future]
            results[index] = future.result()

    # None 제거
    results = [r for r in results if r]

    session["results"] = results

    return render_template_string("""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>검색 결과</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<div class="container mt-5">
<h3 class="mb-4">검색 결과</h3>

<form method="POST" action="/download">
<button class="btn btn-success mb-3">엑셀 다운로드</button>
</form>

<div class="table-responsive">
<table class="table table-bordered table-striped">
<thead class="table-dark">
<tr>
<th>책 제목</th>
<th>PC</th>
<th>모바일</th>
<th>총합</th>
</tr>
</thead>
<tbody>
{% for r in results %}
<tr>
<td>{{r.keyword}}</td>
<td>{{r.pc}}</td>
<td>{{r.mobile}}</td>
<td><strong>{{r.total}}</strong></td>
</tr>
{% endfor %}
</tbody>
</table>
</div>

<a href="/" class="btn btn-secondary mt-3">다시 검색</a>
</div>
</body>
</html>
""", results=results)

# ===============================
# 엑셀 다운로드
# ===============================
@app.route("/download", methods=["POST"])
def download():
    data = session.get("results", [])
    df = pd.DataFrame(data)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="bookvpro_result.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ===============================
# 실행
# ===============================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
