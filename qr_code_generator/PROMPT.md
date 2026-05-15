# QR Code Generator Prototype

## System Requirements

Build a dynamic QR code system where:
- Users submit a long URL and get back a short URL token + QR code image
- The QR code encodes a short URL that redirects (302) to the original URL via your server
- Users can modify the target URL after QR code creation
- Users can delete a QR code (soft delete)
- Users can optionally set an expiration timestamp on create or update
- Deleted or expired links return appropriate HTTP status codes
- URL validation: format check, normalization, malicious URL blocking

## Design Questions

Answer these before you start coding:

1. **Static vs Dynamic QR Code:** Why does this system use dynamic QR codes (encode short URL) instead of static (encode original URL directly)? When would you choose static instead?
A: 短網址的 Payload Size 比較短，且能做 Routing Control，並且因為會做 redirection 所以可以做數據追蹤與分析

2. **Token Generation:** How will you generate short URL tokens? What happens when two different URLs produce the same token? How does collision probability change as the number of tokens grows?
A: 用 url + user_id 去做 base62 演算法產生 token，如果兩個不同的網站做出 same token，資料庫會拒絕寫入而發生攔截異常，碰撞機率變化不確定，反正是越來越高

3. **Redirect Strategy:** Why 302 (temporary) instead of 301 (permanent)? What are the trade-offs for analytics, URL modification, and latency?
A: temporary 在對方修改 URL 後，下次 request 就會立刻被導向新的目標網址，而 permanent 就不能這樣切換，然後 permanent 會直接用 cache 記起來，雖然可以降低伺服器附載與跳轉延遲，但很難更新目標網址與做數據追蹤

4. **URL Normalization:** What normalization rules do you need? Why is `http://Example.com/` and `https://example.com` potentially the same URL?
A: Normalization rules: url 全小寫，並且轉換網址到格式符合 https://domain/path 這種形式

5. **Error Semantics:** What should happen when someone scans a deleted link vs a non-existent link? Should the HTTP status codes be different?
A: 嚴格語意上來說，掃到 deleted link，要回傳 404，掃到 non-existent link，要回傳 410，但以資安來說好像都回傳 404 就好

## Verification

Your prototype should pass all of these:

```bash
# Create a QR code
curl -X POST http://localhost:8000/api/qr/create \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
# → 200, returns {"token": "...", "short_url": "...", "qr_code_url": "...", "original_url": "..."}

# Redirect
curl -o /dev/null -w "%{http_code}" http://localhost:8000/r/{token}
# → 302

# Get info
curl http://localhost:8000/api/qr/{token}
# → 200, returns token metadata

# Update target URL
curl -X PATCH http://localhost:8000/api/qr/{token} \
  -H "Content-Type: application/json" \
  -d '{"url": "https://new-url.com"}'
# → 200

# Redirect now goes to new URL
curl -o /dev/null -w "%{redirect_url}" http://localhost:8000/r/{token}
# → https://new-url.com

# Delete
curl -X DELETE http://localhost:8000/api/qr/{token}
# → 200

# Redirect after delete
curl -o /dev/null -w "%{http_code}" http://localhost:8000/r/{token}
# → 410

# Non-existent token
curl -o /dev/null -w "%{http_code}" http://localhost:8000/r/INVALID
# → 404

# QR code image
# (create a new one first, then)
curl -o /dev/null -w "%{http_code} %{content_type}" http://localhost:8000/api/qr/{token}/image
# → 200 image/png

# Analytics
curl http://localhost:8000/api/qr/{token}/analytics
# → 200, returns {"token": "...", "total_scans": N, "scans_by_day": [...]}
```

## Suggested Tech Stack

Python + FastAPI recommended, but you may use any language/framework.
