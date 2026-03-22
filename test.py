import os, requests
from dotenv import load_dotenv
load_dotenv()
resp = requests.get(
    "https://openrouter.ai/api/v1/models",
    headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
)

free = [
    m["id"] for m in resp.json()["data"]
    if str(m.get("pricing", {}).get("prompt", "1")) == "0"
]

for m in sorted(free):
    print(m)