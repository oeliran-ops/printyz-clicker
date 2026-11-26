"""PRINTYZ website (FastAPI). Run: uvicorn printyz_web.app:app  (settings via environment)."""

from __future__ import annotations

import asyncio
import hmac
import io
import secrets
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from printyz_clicker.config.customer_policy import CustomerPolicy, FilamentColor
from printyz_clicker.edition import policy_path

from . import engine, notify
from .db import DB, STATUSES
from .pricing import PricingRules
from .settings import Settings

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "printyz_clicker" / "assets"


def create_app(settings: Settings | None = None, workers: ProcessPoolExecutor | None = None) -> FastAPI:
    s = settings or Settings()
    db = DB(s.db_path)
    if db.get("policy") is None:                       # first start: the developer's customer policy
        db.put("policy", CustomerPolicy.load(policy_path()).to_dict())
    if db.get("pricing") is None:
        db.put("pricing", PricingRules().to_dict())
    if workers is None:
        import multiprocessing as mp

        # "spawn": forking a server process that already runs threads can deadlock the worker
        workers = ProcessPoolExecutor(max_workers=max(1, s.workers), mp_context=mp.get_context("spawn"))
        for _ in range(max(1, s.workers)):      # warm up: import OCC + load fonts before the first customer
            workers.submit(engine.warm_up)
    pool = workers

    app = FastAPI(title=s.site_name, docs_url=None, redoc_url=None)
    app.add_middleware(SessionMiddleware, secret_key=s.secret_key, same_site="lax", https_only=s.base_url.startswith("https"))
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    tpl = Jinja2Templates(directory=HERE / "templates")
    tpl.env.globals.update(site=s.site_name, statuses=STATUSES)
    tpl.env.filters["datetime"] = lambda t: time.strftime("%d/%m/%Y %H:%M", time.localtime(t))
    app.state.db, app.state.settings, app.state.pool = db, s, pool

    def policy() -> CustomerPolicy:
        return CustomerPolicy.from_dict(db.get("policy"))

    def pricing() -> dict:
        return db.get("pricing")

    async def in_pool(fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(pool, partial(fn, *args))

    def page(request: Request, name: str, **ctx):
        ctx.setdefault("contact", db.get("contact", {}))
        return tpl.TemplateResponse(request, name, ctx)

    # ======================================================================== public pages
    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return page(request, "home.html", products=db.products()[:6], posts=db.posts()[:5])

    @app.get("/gallery", response_class=HTMLResponse)
    def gallery(request: Request):
        return page(request, "gallery.html", products=db.products())

    @app.get("/gallery/{pid}", response_class=HTMLResponse)
    def product(request: Request, pid: int):
        prod = db.product(pid)
        if not prod or not prod["visible"]:
            raise HTTPException(404)
        return page(request, "product.html", product=prod)

    @app.get("/clicker", response_class=HTMLResponse)
    def clicker(request: Request):
        return page(request, "clicker.html")

    @app.get("/order/{token}", response_class=HTMLResponse)
    def track(request: Request, token: str):
        o = db.order_by_token(token)
        if not o:
            raise HTTPException(404)
        return page(request, "order_track.html", o=o)

    @app.get("/uploads/{name}")
    def upload(name: str):
        f = (s.data_dir / "uploads" / Path(name).name)
        if not f.exists():
            raise HTTPException(404)
        return FileResponse(f)

    @app.get("/thumbs/{name}")
    def thumb(name: str):
        f = ASSETS / "thumbs" / Path(name).name
        if not f.exists():
            raise HTTPException(404)
        return FileResponse(f, headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/fonts/{fid}")
    def font_file(fid: str):
        e = engine.fonts().fonts.get(fid)
        if not e or not e.approved:
            raise HTTPException(404)
        return FileResponse(e.path, media_type="font/ttf")

    # ======================================================================== configurator API
    @app.get("/api/config")
    def config():
        from printyz_clicker.geometry.symbols import SYMBOLS, sketch_to_svg, symbol_sketch

        pol = policy()
        reg = engine.fonts()
        allowed = set(pol.fonts) if pol.fonts else {f.id for f in reg.customer_fonts()}
        fams: dict[str, dict] = {}
        for f in reg.customer_fonts():
            if f.id in allowed and (f.family not in fams or f.weight > fams[f.family]["weight"]):
                fams[f.family] = {"id": f.id, "family": f.family, "weight": f.weight, "hebrew": f.supports_hebrew}
        lib = db.get("hidden_symbols", [])
        symbols = ([{"id": k, "name": v[0], "svg": sketch_to_svg(symbol_sketch(k))} for k, v in SYMBOLS.items()
                    if k not in lib] if pol.symbols_allowed else [])
        return {
            "colors": [{"name": c.name, "hex": c.hex} for c in pol.stock_colors()],
            "defaults": {"body": pol.default_body, "cap": pol.default_cap, "legend": pol.default_legend},
            "fonts": sorted(fams.values(), key=lambda f: (not f["hebrew"], f["family"].lower())),
            "textures": pol.textures, "keycaps": pol.keycap_styles, "layouts": pol.layouts,
            "modes": pol.legend_modes, "max_keys": pol.max_keys, "keychain": pol.keychain,
            "symbols": symbols, "pricing": pricing(), "shop": {"name": pol.shop_name, "contact": pol.shop_contact},
        }

    @app.post("/api/preview")
    async def api_preview(request: Request):
        data = await request.json()
        return JSONResponse(await in_pool(engine.preview, data, db.get("policy"), pricing()))

    @app.post("/api/orders")
    async def api_order(request: Request):
        body = await request.json()
        c = body.get("customer") or {}
        name, email, phone = (str(c.get(k, "")).strip()[:120] for k in ("name", "email", "phone"))
        if not name or "@" not in email or len("".join(ch for ch in phone if ch.isdigit())) < 9:
            raise HTTPException(400, "נא למלא שם, אימייל וטלפון תקינים.")
        if not c.get("terms"):
            raise HTTPException(400, "יש לאשר את תנאי השימוש.")
        customer = {"name": name, "email": email, "contact": phone, "notes": str(c.get("notes", ""))[:1000]}
        tmp = s.data_dir / "orders" / f"tmp-{secrets.token_hex(8)}.printyz-order"
        res = await in_pool(engine.make_order_file, body.get("design") or {}, db.get("policy"), pricing(),
                            customer, str(tmp))
        if res["errors"]:
            tmp.unlink(missing_ok=True)
            raise HTTPException(400, " ".join(res["errors"]))
        o = db.create_order(name=name, email=email, phone=phone, notes=customer["notes"],
                            marketing=bool(c.get("marketing")), summary=res["summary"], project=res["project"],
                            price=res["price"], breakdown=res["price_lines"])
        order_file = s.data_dir / "orders" / f"order-{o['id']}.printyz-order"
        tmp.rename(order_file)
        track_url = f"{s.base_url}/order/{o['token']}"
        admin_url = f"{s.base_url}/admin/orders/{o['id']}"
        txt = o["summary"].get("text", "")
        if s.owner_email:
            notify.send_email(s, s.owner_email, f"הזמנה חדשה #{o['id']} — {txt} — ₪{o['price']:g}",
                              f"התקבלה הזמנה חדשה מ־{name} ({phone}, {email}).\n\n"
                              f"טקסט: {txt}\nמחיר: ₪{o['price']:g}\nהערות: {customer['notes'] or '—'}\n"
                              f"דיוור: {'כן' if c.get('marketing') else 'לא'}\n\nלאישור: {admin_url}\n",
                              attachments=[(order_file.name, order_file.read_bytes(), "application/zip")])
        notify.whatsapp_owner(s, f"🛎 הזמנה חדשה #{o['id']} מ־{name}: קליקר \"{txt}\" ₪{o['price']:g}\n{admin_url}")
        notify.send_email(s, email, f"קיבלנו את ההזמנה שלך #{o['id']} — {s.site_name}",
                          f"שלום {name},\n\nקיבלנו את ההזמנה שלך (קליקר \"{txt}\", ₪{o['price']:g}).\n"
                          f"נבדוק אותה ונשלח לך אישור וקישור לתשלום.\n\nמעקב אחרי ההזמנה: {track_url}\n\n{s.site_name}")
        return {"id": o["id"], "track_url": f"/order/{o['token']}"}

    # ======================================================================== admin
    def require_admin(request: Request):
        if not request.session.get("admin"):
            raise HTTPException(303, headers={"Location": "/admin/login"})

    def check_csrf(request: Request, token: str):
        if not token or not hmac.compare_digest(token, request.session.get("csrf", "")):
            raise HTTPException(400, "Invalid form token")

    def admin_page(request: Request, name: str, **ctx):
        request.session.setdefault("csrf", secrets.token_urlsafe(16))
        ctx["csrf"] = request.session["csrf"]
        return page(request, name, **ctx)

    @app.get("/admin/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return admin_page(request, "admin/login.html", error="")

    _fails: dict[str, list[float]] = {}

    @app.post("/admin/login")
    def login(request: Request, password: str = Form(...)):
        ip = request.client.host if request.client else "?"
        recent = [t for t in _fails.get(ip, []) if time.time() - t < 600]
        if len(recent) >= 8:
            return admin_page(request, "admin/login.html", error="יותר מדי ניסיונות. נסו שוב בעוד כמה דקות.")
        if s.admin_password and hmac.compare_digest(password, s.admin_password):
            request.session.clear()
            request.session["admin"] = True
            request.session["csrf"] = secrets.token_urlsafe(16)
            return RedirectResponse("/admin", 303)
        _fails[ip] = recent + [time.time()]
        return admin_page(request, "admin/login.html", error="סיסמה שגויה.")

    @app.get("/admin/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/", 303)

    @app.get("/admin", response_class=HTMLResponse)
    def admin_home(request: Request, status: str | None = None):
        require_admin(request)
        return admin_page(request, "admin/orders.html", orders=db.orders(status), status=status)

    @app.get("/admin/orders/{oid}", response_class=HTMLResponse)
    def admin_order(request: Request, oid: int):
        require_admin(request)
        o = db.order(oid)
        if not o:
            raise HTTPException(404)
        msg = customer_message(o)
        return admin_page(request, "admin/order.html", o=o, wa=notify.wa_link(o["phone"], msg) if msg else "",
                          track=f"{s.base_url}/order/{o['token']}")

    @app.get("/admin/orders/{oid}/file")
    def admin_order_file(request: Request, oid: int):
        require_admin(request)
        f = s.data_dir / "orders" / f"order-{oid}.printyz-order"
        if not f.exists():
            raise HTTPException(404)
        return FileResponse(f, filename=f.name, media_type="application/zip")

    @app.get("/admin/orders/{oid}/preview.png")
    def admin_order_preview(request: Request, oid: int):
        require_admin(request)
        import zipfile

        f = s.data_dir / "orders" / f"order-{oid}.printyz-order"
        with zipfile.ZipFile(f) as z:
            return Response(z.read("preview_iso.png"), media_type="image/png")

    def customer_message(o: dict) -> str:
        track = f"{s.base_url}/order/{o['token']}"
        st = o["status"]
        name, txt = o["name"], o["summary"].get("text", "")
        if st == "approved":
            return (f"שלום {name}, ההזמנה שלך #{o['id']} (קליקר \"{txt}\") אושרה ✅\n"
                    f"לתשלום ₪{(o['final_price'] or o['price']):g}: {o['payment_link'] or 'פרטים במייל'}\nמעקב: {track}")
        if st == "in_production":
            return (f"שלום {name}, התשלום התקבל והקליקר שלך בייצור 🛠\n"
                    f"צפוי להיות מוכן בעוד כ־{o['ready_days'] or '?'} ימים.\nמעקב: {track}")
        if st == "ready":
            return f"שלום {name}, הקליקר שלך מוכן! 🎉\nמעקב: {track}"
        if st == "rejected":
            return f"שלום {name}, לגבי ההזמנה #{o['id']}: {o['admin_note'] or 'נשמח לדבר איתך על ההזמנה.'}"
        return ""

    def email_customer(o: dict) -> None:
        msg = customer_message(o)
        if msg:
            notify.send_email(s, o["email"], f"עדכון להזמנה #{o['id']}: {STATUSES.get(o['status'])} — {s.site_name}",
                              msg + f"\n\n{s.site_name}")

    @app.post("/admin/orders/{oid}")
    def admin_order_action(request: Request, oid: int, action: str = Form(...), csrf: str = Form(""),
                           final_price: str = Form(""), payment_link: str = Form(""), ready_days: str = Form(""),
                           admin_note: str = Form("")):
        require_admin(request)
        check_csrf(request, csrf)
        o = db.order(oid)
        if not o:
            raise HTTPException(404)
        f: dict = {}
        if admin_note:
            f["admin_note"] = admin_note[:1000]
        if action == "approve":
            f["final_price"] = float(final_price) if final_price else o["price"]
            f["payment_link"] = payment_link.strip()[:500]
            o = db.update_order(oid, status="approved", note="אושרה", **f)
        elif action == "reject":
            o = db.update_order(oid, status="rejected", note=admin_note or "נדחתה", **f)
        elif action == "paid":
            o = db.update_order(oid, status="paid", note="התשלום התקבל", **f)
        elif action == "production":
            f["ready_days"] = int(ready_days) if ready_days.isdigit() else None
            o = db.update_order(oid, status="in_production", note=f"בייצור, {ready_days} ימים", **f)
        elif action in ("ready", "delivered", "cancelled"):
            o = db.update_order(oid, status=action, note=STATUSES[action], **f)
        elif action == "note":
            o = db.update_order(oid, **f)
        else:
            raise HTTPException(400)
        if action in ("approve", "reject", "production", "ready"):
            email_customer(o)
        return RedirectResponse(f"/admin/orders/{oid}", 303)

    # ---- shop settings: stock colours, pricing, contact ----------------------------------------
    @app.get("/admin/settings", response_class=HTMLResponse)
    def admin_settings(request: Request):
        require_admin(request)
        return admin_page(request, "admin/settings.html", pol=policy(), pr=PricingRules.from_dict(pricing()),
                          contact=db.get("contact", {}), fonts=engine.fonts().customer_fonts())

    @app.post("/admin/settings")
    async def admin_settings_save(request: Request):
        require_admin(request)
        form = await request.form()
        check_csrf(request, form.get("csrf", ""))
        pol = policy()
        names, hexes, stock = form.getlist("color_name"), form.getlist("color_hex"), set(form.getlist("color_stock"))
        pol.colors = [FilamentColor(n.strip()[:40], h.upper()[:7], str(i) in stock)
                      for i, (n, h) in enumerate(zip(names, hexes)) if n.strip() and h.startswith("#")]
        if form.get("new_color_name", "").strip():
            pol.colors.append(FilamentColor(form["new_color_name"].strip()[:40], form.get("new_color_hex", "#9AA0A6").upper()))
        for k in ("textures", "keycap_styles", "layouts", "legend_modes"):
            v = form.getlist(k)
            if v:
                setattr(pol, k, v)
        pol.max_keys = max(1, min(10, int(form.get("max_keys", pol.max_keys))))
        pol.keychain = "keychain" in form
        pol.symbols_allowed = "symbols_allowed" in form
        stock_hex = [c.hex for c in pol.stock_colors()]
        for k in ("default_body", "default_cap", "default_legend"):
            if form.get(k) in stock_hex:
                setattr(pol, k, form[k])
        pol.shop_name = form.get("shop_name", pol.shop_name)[:60]
        db.put("policy", pol.to_dict())
        pr = PricingRules.from_dict({k: form.get(f"price_{k}", v) for k, v in PricingRules().to_dict().items()})
        db.put("pricing", pr.to_dict())
        db.put("contact", {k: form.get(f"contact_{k}", "")[:200] for k in
                           ("phone", "whatsapp", "email", "instagram", "facebook", "about")})
        return RedirectResponse("/admin/settings?saved=1", 303)

    # ---- gallery ------------------------------------------------------------------------------
    @app.get("/admin/products", response_class=HTMLResponse)
    def admin_products(request: Request):
        require_admin(request)
        return admin_page(request, "admin/products.html", products=db.products(False))

    @app.post("/admin/products")
    async def admin_product_save(request: Request, csrf: str = Form(""), pid: str = Form(""), title: str = Form(...),
                                 description: str = Form(""), price: str = Form(""), visible: str = Form(""),
                                 images: list[UploadFile] = File(default=[]), delete: str = Form("")):
        require_admin(request)
        check_csrf(request, csrf)
        if delete and pid:
            db.delete_product(int(pid))
            return RedirectResponse("/admin/products", 303)
        current = db.product(int(pid))["images"] if pid else []
        for up in images:
            if up.filename:
                current.append(await save_image(up))
        db.save_product(int(pid) if pid else None, title=title[:120], description=description[:4000],
                        price=price[:40], visible=int(bool(visible)), images=current)
        return RedirectResponse("/admin/products", 303)

    async def save_image(up: UploadFile) -> str:
        from PIL import Image

        data = await up.read()
        if len(data) > 12 * 1024 * 1024:
            raise HTTPException(400, "Image too large (max 12 MB)")
        try:
            img = Image.open(io.BytesIO(data))
            img = img.convert("RGB")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, "Not an image") from e
        img.thumbnail((1600, 1600))
        name = f"{secrets.token_hex(8)}.jpg"
        img.save(s.data_dir / "uploads" / name, "JPEG", quality=85, optimize=True)
        return name

    # ---- updates (posts) ----------------------------------------------------------------------
    @app.get("/admin/posts", response_class=HTMLResponse)
    def admin_posts(request: Request):
        require_admin(request)
        return admin_page(request, "admin/posts.html", posts=db.posts(False))

    @app.post("/admin/posts")
    def admin_post_save(request: Request, csrf: str = Form(""), pid: str = Form(""), title: str = Form(""),
                        body: str = Form(""), visible: str = Form(""), delete: str = Form("")):
        require_admin(request)
        check_csrf(request, csrf)
        if delete and pid:
            db.delete_post(int(pid))
        elif title.strip():
            db.save_post(int(pid) if pid else None, title[:200], body[:6000], bool(visible))
        return RedirectResponse("/admin/posts", 303)

    # ---- marketing list -----------------------------------------------------------------------
    @app.get("/admin/subscribers", response_class=HTMLResponse)
    def admin_subs(request: Request):
        require_admin(request)
        return admin_page(request, "admin/subscribers.html", subs=db.subscribers())

    @app.get("/admin/subscribers.csv")
    def admin_subs_csv(request: Request):
        require_admin(request)
        import csv

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["name", "email", "phone"])
        for r in db.subscribers():                 # neutralise spreadsheet formulas
            w.writerow([("'" + v) if str(v)[:1] and str(v)[0] in "=+-@" else v for v in (r["name"], r["email"], r["phone"])])
        rows = [buf.getvalue()]
        return Response("\ufeff" + rows[0], media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=subscribers.csv"})

    # registered last: a catch-all path must not shadow /admin
    @app.get("/{doc}", response_class=HTMLResponse)
    def legal(request: Request, doc: str):
        if doc not in ("accessibility", "privacy", "terms"):
            raise HTTPException(404)
        return page(request, f"{doc}.html")

    return app


def __getattr__(name):            # `uvicorn printyz_web.app:app` creates the app lazily
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
