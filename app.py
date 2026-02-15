from flask import Flask, request, render_template_string, send_file
import requests
import os
import json
import pandas as pd
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# 네이버 API 환경변수
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")

# 간단 캐시
cache = {}

# -----------------------------
# 네이버 검색 함수
# -----------------------------
def search_keyword(keyword):
    if keyword in cache:
        return cache[keyword]

    url = "https://openapi.naver.com/v1/search/adult.json"
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET
    }

    params = {
        "query": keyword,
        "display": 1
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        data = response.json()

        result = {
            "keyword": keyword,
            "pc": data.get("pcSearchCount", 0),
            "mobile": data.get("mobileSearchCount", 0)
        }
        result["total"] = result["pc"] + result["mobile"]

        cache[keyword] = result
        return result

    except:
        return {
            "keyword": keyword,
            "pc": 0,
            "mobile": 0,
            "total": 0
        }

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
<style>
body { background:#f5f7fa; }
.container { max-width:900px; }
textarea { resize:none; }
</style>
</head>
<body>

<div class="container mt-5">
    <h2 class="text-center mb-4">📚 BookVPro 검색 시스템</h2>

    <form method="POST" action="/search" onsubmit="showLoading()">
        <textarea class="form-control mb-3" name="books" rows="10"
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
# 검색 처리 (병렬)
# -----------------------------
@app.route("/search", methods=["POST"])
def search():
    books = request.form.get("books").split("\n")
    books = [b.strip() for b in books if b.strip()]

    results = []

    with ThreadPoolExecutor(max_workers=10) as executor:
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
<body>

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
                <th>PC 검색량</th>
                <th>모바일 검색량</th>
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

# -----------------------------
# 실행
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
