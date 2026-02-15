import os
import time
import hashlib
import hmac
import base64
import requests
import pandas as pd
from flask import Flask, render_template_string, request, send_file, session
from io import BytesIO

# 환경변수
ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")
CUSTOMER_ID = os.environ.get("CUSTOMER_ID")

BASE_URL = "https://api.searchad.naver.com"

app = Flask(__name__)
app.secret_key = "bookvpro_secret_key"


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
        return []

    return response.json().get("keywordList", [])


def convert_to_int(value):
    if isinstance(value, str) and "<" in value:
        return 0
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

<h3 class="mb-4">📚 BookVPro - 대량 검색</h3>

<form method="post">
<textarea name="keywords" class="form-control mb-3" rows="8"
placeholder="한 줄에 한 권씩 입력하세요 (최대 1000권)"></textarea>

<div class="form-check mb-3">
<input class="form-check-input" type="checkbox" name="include_related" id="include_related">
<label class="form-check-label" for="include_related">
연관 키워드 포함
</label>
</div>

<button type="submit" class="btn btn-primary">검색</button>
</form>

{% if results %}
<hr>

<form method="post" action="/download">
<div class="table-responsive">
<table class="table table-bordered table-striped">
<thead class="table-dark">
<tr>
<th>원본 책 제목</th>
<th>키워드</th>
<th>PC</th>
<th>모바일</th>
<th>총합</th>
</tr>
</thead>
<tbody>
{% for r in results %}
<tr>
<td>{{ r.original }}</td>
<td>{{ r.keyword }}</td>
<td>{{ r.pc }}</td>
<td>{{ r.mobile }}</td>
<td>{{ r.total }}</td>
</tr>
{% endfor %}
</tbody>
</table>
</div>

<button class="btn btn-success mt-2">엑셀 다운로드</button>
</form>
{% endif %}

</div>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    results = []

    if request.method == "POST":
        keywords_raw = request.form.get("keywords")
        include_related = request.form.get("include_related")

        keywords = [k.strip() for k in keywords_raw.splitlines() if k.strip()]

        for kw in keywords:
            data = get_keyword_volume(kw)
            time.sleep(0.25)  # API 과부하 방지

            for item in data:
                rel_keyword = item["relKeyword"]

                if not include_related:
                    if rel_keyword.replace(" ", "") != kw.replace(" ", ""):
                        continue

                pc = convert_to_int(item["monthlyPcQcCnt"])
                mobile = convert_to_int(item["monthlyMobileQcCnt"])
                total = pc + mobile

                results.append({
                    "original": kw,
                    "keyword": rel_keyword,
                    "pc": pc,
                    "mobile": mobile,
                    "total": total
                })

    session["results"] = results
    return render_template_string(HTML, results=results)


@app.route("/download", methods=["POST"])
def download():
    data = session.get("results", [])

    df = pd.DataFrame(data)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="bookvpro_result.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


if __name__ == "__main__":
    app.run()
