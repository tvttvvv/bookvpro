import os
import time
import hashlib
import hmac
import base64
import requests
import pandas as pd
from flask import Flask, render_template_string, request, send_file
from io import BytesIO

ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")
CUSTOMER_ID = os.environ.get("CUSTOMER_ID")

BASE_URL = "https://api.searchad.naver.com"

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

<h3>📚 BookVPro - 대량 검색</h3>

<form method="post">
<textarea name="keywords" class="form-control mb-3" rows="6"
placeholder="한 줄에 한 권씩 입력하세요"></textarea>

<button type="submit" class="btn btn-primary">검색</button>
</form>

{% if results %}
<hr>
<form method="post" action="/download">
<table class="table table-bordered table-striped">
<thead class="table-dark">
<tr>
<th>책 제목</th>
<th>키워드</th>
<th>PC</th>
<th>모바일</th>
<th>총합</th>
<th>연관 포함</th>
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
<td>
<input type="checkbox" name="related_{{ loop.index0 }}">
</td>
</tr>
{% endfor %}
</tbody>
</table>

<input type="hidden" name="data" value="{{ results|tojson }}">
<button class="btn btn-success">엑셀 다운로드</button>
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
        keywords = [k.strip() for k in keywords_raw.splitlines() if k.strip()]

        for kw in keywords:
            data = get_keyword_volume(kw)
            time.sleep(0.3)

            for item in data:
                rel_keyword = item["relKeyword"]
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

    return render_template_string(HTML, results=results)

@app.route("/download", methods=["POST"])
def download():
    import json
    data = json.loads(request.form.get("data"))

    df = pd.DataFrame(data)
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(output,
                     as_attachment=True,
                     download_name="bookvpro_result.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == "__main__":
    app.run()
