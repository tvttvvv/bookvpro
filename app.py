import os
import time
import hashlib
import hmac
import base64
import requests
from flask import Flask, render_template_string, request

# 환경변수에서 API 키 불러오기
ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")
CUSTOMER_ID = os.environ.get("CUSTOMER_ID")

BASE_URL = "https://api.naver.com"

app = Flask(__name__)

def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        bytes(message, "utf-8"),
        hashlib.sha256
    ).digest()
    return base64.b64encode(signature)

def get_keyword_volume(keyword):
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

    response = requests.get(BASE_URL + uri, headers=headers, params=params)

    if response.status_code != 200:
        return None

    return response.json()

def convert_to_int(value):
    if isinstance(value, str):
        if "<" in value:
            return 0
        return int(value)
    return int(value)

HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BookVPro</title>

<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">

</head>
<body class="bg-light">

<div class="container mt-4">

<h3 class="mb-4">📚 BookVPro - 책 검색량 조회</h3>

<form method="post" class="row g-2 mb-4">
    <div class="col-12 col-md-6">
        <input type="text" name="keyword" class="form-control" placeholder="책 제목 입력">
    </div>

    <div class="col-6 col-md-3">
        <div class="form-check">
            <input class="form-check-input" type="checkbox" name="related" id="related">
            <label class="form-check-label" for="related">
                연관 키워드 포함
            </label>
        </div>
    </div>

    <div class="col-6 col-md-3">
        <button type="submit" class="btn btn-primary w-100">검색</button>
    </div>
</form>

{% if results %}
<div class="table-responsive">
<table class="table table-bordered table-striped">
<thead class="table-dark">
<tr>
<th>키워드</th>
<th>PC</th>
<th>모바일</th>
<th>총합</th>
</tr>
</thead>
<tbody>
{% for row in results %}
<tr>
<td>{{ row.keyword }}</td>
<td>{{ row.pc }}</td>
<td>{{ row.mobile }}</td>
<td>{{ row.total }}</td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
{% endif %}

</div>

</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    results = []

    if request.method == "POST":
        keyword = request.form.get("keyword")
        include_related = request.form.get("related")

        data = get_keyword_volume(keyword)

        if data and "keywordList" in data:
            for item in data["keywordList"]:
                rel_keyword = item["relKeyword"]

                if not include_related:
                    if rel_keyword.replace(" ", "") != keyword.replace(" ", ""):
                        continue

                pc = convert_to_int(item["monthlyPcQcCnt"])
                mobile = convert_to_int(item["monthlyMobileQcCnt"])
                total = pc + mobile

                results.append({
                    "keyword": rel_keyword,
                    "pc": pc,
                    "mobile": mobile,
                    "total": total
                })

    return render_template_string(HTML, results=results)

if __name__ == "__main__":
    app.run()
