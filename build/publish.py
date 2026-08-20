"""Wrap a generated chart SVG in a zoomable page, a one-sheet PDF and a PNG."""
import pathlib, re, sys
from playwright.sync_api import sync_playwright

SP = pathlib.Path('/tmp/claude-0/-workspace-Ai-agent/c4d7b8f3-9943-593b-87a1-fcf0a4dfb89e/scratchpad/pdf')
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
DOCS = pathlib.Path('/workspace/Ai-agent/docs')

PAGE = '''<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
  :root{{--bg:#EDF0F4;--surface:#FFFFFF;--border:#D6DDE6;--text:#111823;--dim:#4A5566;
    --faint:#7E8896;--accent:#1F6FB2;--sans:"Archivo",ui-sans-serif,system-ui,sans-serif;
    --mono:"IBM Plex Mono",ui-monospace,monospace}}
  @media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0D1218;--surface:#151C25;
    --border:#2A3340;--text:#E3E9F1;--dim:#9AA5B4;--faint:#6D7887;--accent:#5FA9E2}}}}
  :root[data-theme="dark"]{{--bg:#0D1218;--surface:#151C25;--border:#2A3340;--text:#E3E9F1;
    --dim:#9AA5B4;--faint:#6D7887;--accent:#5FA9E2}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans)}}
  header{{display:flex;flex-wrap:wrap;gap:14px 26px;align-items:baseline;padding:18px 24px;
    background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:5}}
  h1{{font-size:19px;font-weight:700;margin:0;letter-spacing:-.01em}}
  h1 span{{color:var(--accent);font-family:var(--mono)}}
  .meta{{display:flex;gap:22px;flex-wrap:wrap;margin-right:auto}}
  .m{{font-size:12px;color:var(--dim)}}
  .m b{{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.1em;
    text-transform:uppercase;color:var(--faint);font-weight:600}}
  .zoom{{display:flex;gap:6px;align-items:center}}
  button{{font-family:var(--mono);font-size:12px;font-weight:600;color:var(--text);background:var(--bg);
    border:1px solid var(--border);padding:6px 11px;border-radius:3px;cursor:pointer}}
  button:hover{{border-color:var(--accent);color:var(--accent)}}
  button:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
  .hint{{font-size:12px;color:var(--faint);font-family:var(--mono)}}
  .stage{{overflow:auto;padding:22px;height:calc(100vh - 66px)}}
  .sheet{{background:#FFFFFF;border:1px solid var(--border);box-shadow:0 1px 3px rgba(0,0,0,.14);
    width:max-content;margin:0 auto}}
  .sheet svg{{display:block;width:var(--w,1600px);height:auto}}
  @media (max-width:700px){{.stage{{padding:10px}}header{{padding:14px 16px}}}}
</style>
<header>
  <h1>{heading}</h1>
  <div class="meta">{meta}</div>
  <div class="zoom"><span class="hint">zoom</span>
    <button type="button" data-z="out">&minus;</button>
    <button type="button" data-z="fit">fit</button>
    <button type="button" data-z="in">+</button>
    <button type="button" data-z="full">100%</button></div>
</header>
<div class="stage" id="stage"><div class="sheet" id="sheet">
{svg}
</div></div>
<script>
  const sheet=document.getElementById('sheet'),stage=document.getElementById('stage'),NAT={nat};
  let w=1600;
  const apply=()=>sheet.style.setProperty('--w',w+'px');
  const fit=()=>{{w=Math.max(320,stage.clientWidth-46);apply();}};
  document.querySelectorAll('[data-z]').forEach(b=>b.addEventListener('click',()=>{{
    const z=b.dataset.z;
    if(z==='in')w=Math.min(NAT*2,w*1.25);
    if(z==='out')w=Math.max(320,w/1.25);
    if(z==='full')w=NAT;
    if(z==='fit')return fit();
    apply();}}));
  fit();
  addEventListener('resize',()=>{{if(w>stage.clientWidth)fit();}});
</script>
'''

def publish(stem, title, heading, meta_pairs, aria_png=True):
    svg_path = DOCS / f'{stem}.svg'
    raw = svg_path.read_text(encoding='utf-8').split('?>\n', 1)[1]
    vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', raw)
    natw, nath = int(vb.group(1)), int(vb.group(2))
    meta = ''.join(f'<div class="m"><b>{k}</b>{v}</div>' for k, v in meta_pairs)
    html_path = DOCS / f'{stem}.html'
    html_path.write_text(PAGE.format(title=title, heading=heading, meta=meta, svg=raw, nat=natw),
                         encoding='utf-8')

    fonts = (SP / 'fonts/inline.css').read_text(encoding='utf-8')
    # One sheet, proportioned to the drawing so nothing is scaled down to fit a preset size.
    w_in = 22.0
    h_in = round(w_in * nath / natw, 2)
    print_html = SP / f'{stem}.print.html'
    print_html.write_text(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{fonts}\n'
        f'@page{{size:{w_in}in {h_in}in;margin:0.35in}}html,body{{margin:0;background:#fff}}\n'
        f'*{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}\n'
        f'svg{{display:block;width:{w_in - 0.7}in;height:auto}}</style></head><body>{raw}</body></html>',
        encoding='utf-8')

    pdf_path = DOCS / f'{stem}.pdf'
    png_path = DOCS / f'{stem}.png'
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        pg = b.new_page(viewport={"width": 1800, "height": 1200})
        pg.goto("file://" + str(print_html), wait_until="load")
        pg.evaluate("""async () => { await Promise.all(
            ['500 13px Archivo','600 13px Archivo','700 13px Archivo',
             '400 16px "IBM Plex Mono"','600 16px "IBM Plex Mono"','700 16px "IBM Plex Mono"']
            .map(f => document.fonts.load(f))); await document.fonts.ready; }""")
        pg.emulate_media(media="print")
        pg.pdf(path=str(pdf_path), prefer_css_page_size=True, print_background=True)
        pg.evaluate(f"document.querySelector('svg').style.width='{natw}px'")
        pg.set_viewport_size({"width": min(natw, 3600), "height": 1000})
        pg.wait_for_timeout(700)
        pg.screenshot(path=str(png_path), full_page=True)
        b.close()

    raw_pdf = pdf_path.read_bytes()
    pages = re.findall(rb'/MediaBox\s*\[([^\]]*)\]', raw_pdf)
    faces = sorted({n.decode().split('+')[-1] for n in re.findall(rb'/BaseFont\s*/([A-Za-z0-9+\-]+)', raw_pdf)})
    print(f"{stem}: page {html_path.name} | pdf {len(raw_pdf)//1024} KB, {len(pages)} sheet "
          f"{w_in} x {h_in} in | png {png_path.stat().st_size//1024} KB")
    print("   fonts embedded:", [f for f in faces if 'Archivo' in f or 'Plex' in f])

if __name__ == '__main__':
    which = sys.argv[1]
    if which == 'phase1':
        publish('twin-home-buyer-phase1-seller-flow',
                'Phase 1 Seller Call Flow',
                'Twin Home Buyer — Phase 1 Seller Inbound Call Flow',
                [("Scope", "New Seller + Seller Callback only"),
                 ("Status", "For Cherry's review"),
                 ("Build / Retell", "Rosanes"),
                 ("Approval", "Cherry, then Juan")])
    elif which == 'v21':
        publish('twin-home-buyer-call-flow-v2.1',
                'Inbound Retell AI Call Flow',
                'Twin Home Buyer — Inbound Retell AI Call Flow <span>v2.1</span>',
                [("Status", "Updated Build Map"),
                 ("Build / Retell", "Rosanes"),
                 ("Approval", "Juan")])
