import sys, subprocess, pathlib, markdown
src, out_pdf, title = sys.argv[1], str(pathlib.Path(sys.argv[2]).resolve()), sys.argv[3]
fonts = (pathlib.Path(__file__).resolve().parents[2] / "web/app/fonts/Vazirmatn.woff2").as_uri()
body = markdown.markdown(pathlib.Path(src).read_text(), extensions=["tables", "fenced_code", "sane_lists"])
html = f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>{title}</title><style>
@font-face {{ font-family: Vazirmatn; src: url("{fonts}") format("woff2"); font-weight: 100 900; }}
@page {{ size: A4; margin: 16mm 14mm 18mm; }}
body {{ font-family: Vazirmatn, sans-serif; color: #1b1d22; font-size: 11.5pt; line-height: 1.95; }}
h1 {{ font-size: 24pt; margin: 0 0 6pt; color: #0B0D12; border-bottom: 3px solid #F2A93B; padding-bottom: 6pt; }}
h2 {{ font-size: 16pt; margin: 22pt 0 6pt; color: #0B0D12; border-right: 5px solid #F2A93B; padding-right: 10pt; page-break-after: avoid; }}
h3 {{ font-size: 13pt; margin: 14pt 0 4pt; page-break-after: avoid; }}
p {{ margin: 4pt 0 8pt; }} li {{ margin: 2pt 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 8pt 0 12pt; font-size: 10pt; line-height: 1.7; page-break-inside: auto; }}
th, td {{ border: 1px solid #c9ccd4; padding: 5pt 8pt; text-align: right; vertical-align: top; }}
th {{ background: #f3efe6; }} tr {{ page-break-inside: avoid; }}
code {{ font-family: "DejaVu Sans Mono", monospace; direction: ltr; unicode-bidi: embed; background: #f1f2f5; padding: 0 3pt; border-radius: 3pt; font-size: 9.5pt; }}
pre {{ direction: ltr; text-align: left; background: #0f1218; color: #e8e6df; padding: 10pt 12pt; border-radius: 8pt; font-size: 8.4pt; line-height: 1.55; overflow: hidden; page-break-inside: avoid; }}
pre code {{ background: none; color: inherit; padding: 0; font-size: inherit; }}
hr {{ border: 0; border-top: 1px solid #c9ccd4; margin: 16pt 0; }}
a {{ color: #0b57d0; }}
</style></head><body>{body}</body></html>"""
tmp = pathlib.Path(out_pdf).with_suffix(".html"); tmp.write_text(html)
subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", f"--print-to-pdf={out_pdf}", "--no-pdf-header-footer", "--virtual-time-budget=5000", tmp.as_uri()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
tmp.unlink()
print(out_pdf)
