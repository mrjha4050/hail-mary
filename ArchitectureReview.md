# Question A — Django Admin Performance

A primary key index barely helps here — primary keys are indexed automatically, so this "fix"
changed almost nothing. Three real causes to check:

**1. N+1 queries from `list_display`**
If `list_display` shows a field that crosses a foreign key (e.g. `order.customer.name`) or a
method that does its own lookup, Django's admin change-list fires one extra query *per row on
the page*. At 100 rows per page that's 100+ extra round trips before the page even renders.
Fix: add `list_select_related` on the `ModelAdmin`, listing the related fields so Django JOINs
them into the single list query instead of querying per row. For reverse/manyTomany relations
that a JOIN can't fold in the same way, `list_prefetch_related` does the equivalent for those.

**2. Unindexed or wildcard `search_fields`**
If `search_fields` includes an unindexed `CharField`/`TextField`, or spans a related model
(`'customer__name'`), every search does a slow scan across 500k+ rows. Django admin's search
runs an `OR` across every field in `search_fields`, each wrapped in `icontains` — a
leading wildcard `LIKE '%term%'` that can't use a standard B-tree index at all. I've hit this in
production: searching an unindexed field on a large table effectively ran a full table scan per
search field and timed out the request, which looked like the admin panel crashing.
Fix: add `db_index=True` (or a `Meta.indexes` entry) on the actual searched column. If true
free-text search is needed (matching any word, not just a known prefix), use Postgres full-text
search (`SearchVector`) instead of `icontains`-style wildcard matching.

**3. Exact `COUNT(*)` on every page load**
Django's admin paginator runs `COUNT(*)` on the filtered queryset for every single page load to
show total results on a 500k+ row table this itself can be a slow full scan, independent of
the actual data being displayed.
Fix: override `paginator` on the `ModelAdmin` with a custom `Paginator` subclass that either
caches the count or estimates it (e.g. via Postgres's `pg_class.reltuples`) instead of running
an exact count on every request.


# Question B — Pagination Trade-offs

****Offset pagination**** 

(`LIMIT 50 OFFSET 5000`) does not jump straight to row 5000. The database
scans and counts every row before the offset, then throws them away, every time. So page 1 is
fast, but page 200 is slow — the deeper you go, the more rows get scanned and discarded.

It also breaks under writes. If new rows get inserted while a user is scrolling, everything
shifts. A row the user already saw can show up again, or a row can get skipped entirely. This
happens often in a live feed with real insert traffic, and it is a common source of "why do I
see this order twice" bugs.

Good for: static data .simple page-number UIs ("jump to page 40"), tables that don't change much while being
viewed. Easy to build, easy to reason about.

#### example:- Amazon , flipkart use for showing  products . bottom of the page you can see  page number 1,2,3,4,

``GET /orders?limit=50&offset=5000``

``SELECT * FROM orders ORDER BY created_at LIMIT 50 OFFSET 5000;``


****Cursor pagination****

does not use a page number. It uses a pointer to the last row seen — for
example `WHERE created_at < last_seen_timestamp ORDER BY created_at DESC LIMIT 50`. With an
index on `created_at`, the database seeks straight to that point instead of scanning and
discarding everything before it. Page 200 is just as fast as page 1.

It also does not break under writes. New rows added elsewhere don't shift anything, because the
query always says "give me rows after this exact point," not "give me rows after this count."
No duplicates, no skipped rows.

Benefit: you can't jump to an arbitrary page. Cursors only move forward or backward
from where you are, one step at a time.

**When to pick which**

Infinite scroll and live feeds, where data keeps changing and users scroll deep  use cursor
pagination. It fixes both the slow-deep-page problem and the duplicate/skip problem, and those
matter more than jumping to a page number in a scroll UI.

Admin style tables with page links, where the data is fairly static and users want to jump to a
specific page  offset pagination is fine, and simpler to build.

**For this case : 10,000+ records, likely growing, and a mobile app doing infinite scroll  cursor
pagination is the right call.**



# Question C — File Upload Security

**1. Fake file type (extension/MIME spoofing)**
A file can be renamed (`shell.php` → `photo.jpg`) or sent with a fake `Content-Type` — both are
just labels the client controls, not the real file content.
Fix: don't trust the extension or client-supplied MIME type. Check the actual bytes — for
images, run the file through `PIL.Image.open()` and call `.verify()`, which parses it as real
image data and fails on a fake.

**2. Path traversal in the filename**
A filename like `../../settings.py` can write outside the upload folder if used directly in a
save path — e.g. `../etc/passwd`, glued on by string concatenation, can overwrite a file far
outside `MEDIA_ROOT`.
Fix: Django's `FileSystemStorage` already strips this via `get_valid_name()` by default. For any
custom path logic always use the filename through `django.utils.text.get_valid_filename()`
first, never concatenate raw user input into a path.

**3. Stored XSS from uploaded HTML/SVG**
An uploaded `.svg` or `.html` file can hide `<script>` tags; if served back from your own
domain, the browser runs it as your site's own code — e.g. a "profile picture" `avatar.svg`
that actually runs a script for anyone who views it.
Fix: serve uploads from a separate subdomain, isolating any executed script from your main
site's session cookies via same-origin rules, and set `Content-Disposition: attachment` so
browsers download rather than render the file.

**4. Oversized files / decompression bombs**
A small upload can expand into gigabytes once processed — e.g. a 200KB zip that unpacks into
50GB and exhausts memory or disk.
Fix: set `DATA_UPLOAD_MAX_MEMORY_SIZE` and `FILE_UPLOAD_MAX_MEMORY_SIZE` to cap upload size, and
`PIL.Image.MAX_IMAGE_PIXELS` so Pillow refuses to decompress an image bomb.

**5. Uploaded file gets executed as code**
If uploads land in a folder the server can execute — same tree as the app, or a static folder
with script execution on — a `.php` file on disk could actually run when visited directly,
giving remote code execution.
Fix: point `MEDIA_ROOT` at a location completely separate from anywhere the app or static
server executes files, and enforce a strict allow-list of extensions/content-types at the
form/model validation layer, rejecting anything not explicitly permitted rather than
blocklisting dangerous ones.