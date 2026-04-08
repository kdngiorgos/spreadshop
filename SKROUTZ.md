# Skroutz.gr — Developer Reference

Skroutz is the dominant Greek price-comparison marketplace. This doc covers what we currently use, what official APIs exist, and where they might be useful for this project.

---

## What We Currently Use (Unofficial JSON Endpoints)

Skroutz's frontend fetches data via internal JSON endpoints that are accessible with a standard browser User-Agent. No API key or authentication required.

### Search endpoint

```
GET https://www.skroutz.gr/search.json?keyphrase={query}
```

Response: `{ "skus": [...], "redirectUrl": "..." }`

- If `redirectUrl` is present, the search resolved to a single category page. Follow it by replacing `.html` with `.json`.
- If `skus` is present, parse the list and fuzzy-match the query against `name`.

Key fields per SKU object:

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | SKU identifier — used for the second call |
| `name` | string | Product name |
| `sku_url` | string | Relative URL → prepend `https://www.skroutz.gr` |
| `price` | string | Lowest price, e.g. `"1.347,78 €"` (dot = thousands, comma = decimal) |
| `shop_count` | int | Number of shops listing this SKU |
| `review_score` | string | Rating, e.g. `"4,7"` |
| `reviews_count` | int | Number of reviews |

### Filter products endpoint (second step)

```
GET https://www.skroutz.gr/s/{skroutz_id}/filter_products.json
```

Called after finding a matching SKU id. Returns `product_cards` (dict keyed by card id) with `final_price` per variant, and an accurate `shop_count`. Used to set `lowest_price`/`highest_price` on the `SkroutzResult`.

### Implementation

See `scraper/skroutz.py`:
- `_fetch_async()` — search + redirect handling
- `_fetch_filter_products_async()` — second-step price detail
- `_parse_search_results_json()` — JSON → `SkroutzResult`
- `bulk_search_async()` — concurrent execution (asyncio Semaphore, default 5 workers)

---

## Official Merchant API (developer.skroutz.gr)

Skroutz has a documented REST API, but it is **merchant-facing only** — it manages your own shop's listings and orders. It does **not** expose competitor prices or general product lookup. Access requires a merchant account + OAuth 2.0 Bearer token.

**Bottom line for this project**: the official API cannot replace our JSON endpoint scraping. It would only be relevant if the user becomes a Skroutz marketplace seller.

### Authentication

OAuth 2.0 `client_credentials` grant:

```
POST https://www.skroutz.gr/oauth2/token
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
```

Tokens are generated from the merchant panel under Merchants > Services > Skroutz Marketplace. One active key per shop — new key expires the previous one.

Required header on all API calls:
```
Accept: application/vnd.skroutz+json; version=3.0
Authorization: Bearer <token>
```

### Products API

```
POST /merchants/products/batch
```

Bulk-update up to 500 product variants (availability, price, stock quantity). Useful if we ever list supplier products on Skroutz — keeps our storefront in sync with the wholesaler catalog we're already parsing.

```
POST /merchants/products/validate_batch_payload
```

Dry-run validation before submitting.

### Orders API (Smart Cart)

Manage orders received through Skroutz Marketplace:

| Endpoint | Action |
|----------|--------|
| `GET /merchants/ecommerce/orders/:code` | Retrieve order |
| `POST /merchants/ecommerce/orders/:code/accept` | Accept |
| `POST /merchants/ecommerce/orders/:code/reject` | Reject |
| `POST /merchants/ecommerce/orders/:code/invoices` | Upload invoice |
| `POST /merchants/ecommerce/orders/:code/set_as_ready` | Mark ready to ship |
| `POST /merchants/ecommerce/orders/:code/tracking_details` | Update tracking (FBM) |

### Fulfilled by Skroutz (FBS) API

For warehouse/logistics operations if using Skroutz's fulfillment service:
- `GET /merchants/ecommerce/fbs/products` — warehouse inventory
- `GET/POST /merchants/ecommerce/fbs/purchase_orders` — restock orders
- `GET/POST/PATCH /merchants/ecommerce/fbs/suppliers` — supplier management

### CPS Orders API

Cost-per-sale model:
- `GET /merchants/cps/orders/:order_code`
- `POST /merchants/cps/orders/:order_id/reject`

---

## Webhooks

Skroutz pushes order lifecycle events to a URL you register in the merchant panel.

**Events**: new order, accepted, rejected, expired, dispatched, cancelled, partially_returned, returned

**Retry policy**: up to 4 attempts within 20 minutes on non-200 responses or timeouts.

**Originating IPs** (whitelist these if behind a firewall):
- `185.6.76.0/22`
- `2a03:e40::/32`

Payload includes order code, customer info, line items with pricing, commissions, courier/tracking, and VAT details.

---

## Python Client Libraries

| Library | Type | Notes |
|---------|------|-------|
| `pyskroutz` | Unofficial (PyPI) | `pip install pyskroutz` — basic search and API access |
| `skroutz.ex` | Official (Elixir) | github.com/skroutz/skroutz.ex |
| `clj-skroutz` | Official (Clojure) | github.com/skroutz/clj-skroutz |

`pyskroutz` is the only Python option; it's unofficial and unmaintained — our direct httpx approach is more reliable.

---

## Resources

- Developer docs: https://developer.skroutz.gr/
- Merchant portal: https://merchants.skroutz.gr/merchants
- Engineering blog: https://engineering.skroutz.gr/
- GitHub (open source tools): https://github.com/skroutz
- Community Swagger UI: https://github.com/KAUTH/Swagger-Skroutz-API
- Partner support: https://partnersupport.skroutz.gr/hc/en-us
