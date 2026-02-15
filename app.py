import os
import time
import hashlib
import hmac
import base64
import requests
import pandas as pd
from flask import Flask, request, render_template_string, send_file
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")
CUSTOMER_ID = os.environ.get("CUSTOMER_ID")

BASE_URL = "https://api.searchad.naver.com"
app = Flask(__name__)

cache = {}

# -----------------------------
# 서명 생성
# -----------------------------
def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        bytes(message, "utf-8"),
        hashlib.sha256
    ).digest()
    return base64.b64encode(signature).decode()

# -----------------------------
# 검색 함수
# -----------------------------
def search_keyword(keyword):
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
        response = requests.get(BASE_URL + uri, headers=headers, params=params, timeout=5)

        if response.status_code != 200:
            return {"keyword": keyword, "pc": 0, "mobile": 0, "total": 0}

        data = response.json().get("keywordList", [])

        if not data:
            return {"keyword": keyword, "pc": 0, "mobile": 0, "total": 0}

        item = data[0]

        pc = int(item["monthlyPcQcCnt"].replace("< 10", "0")) if isinstance(item["monthlyPcQcCnt"], str) else int(item["monthlyPcQcCnt"])
        mobile = int(item["monthlyMobileQcCnt"].replace("< 10", "0")) if isinstance(item["monthlyMobileQcCnt"], str) else int(item["monthlyMobileQcCnt"])

        result = {
            "keyword": keyword,
            "pc": pc,
            "mobile": mobile,
            "total": pc + mobile
        }

        cache[keyword] = result
        return result

    except:
        return {"keyword": keyword, "pc": 0, "mobile": 0, "total": 0}

# -----------------------------
# 메인 페이지
# -----------------------------
@app.route("/")
def home():
    return render_template_string("""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>BookVPro</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<div class="container mt-5">
<h2 class="mb-4 text-center">📚 BookVPro 검색 시스템</h2>
<form method="POST" action="/search" onsubmit="showLoading()">
<textarea name="books" class="form-control mb-3" rows="8"
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

# -----------------------------
# 병렬 검색
# -----------------------------
@app.route("/search", methods=["POST"])
def search():
    books = request.form.get("books").split("\n")
    books = [b.strip() for b in books if b.strip()]

    results = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(search_keyword, b) for b in books]
        for future in as_completed(futures):
            results.append(future.result())

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
<input type="hidden" name="data" value='{{results|tojson}}'>
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

# -----------------------------
# 엑셀 다운로드
# -----------------------------
@app.route("/download", methods=["POST"])
def download():
    import json
    data = json.loads(request.form.get("data"))
    df = pd.DataFrame(data)

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="bookvpro_result.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
