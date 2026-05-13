# html_generator.py  v3
# Conditional section rendering via selected_sections dict.
# INR 5-day line chart replaced with WoW % change bar chart (Bloomberg open/close only).
# Gold shown as international XAU/USD price.
# Brent chart uses yfinance 5-day series (no USD/INR overlay).

from datetime import datetime

# ── SVG: INR WoW % change bar chart ──────────────────────────────────────────

def build_inr_change_chart(data, selected_fx_pairs):
    """
    Horizontal bar chart: WoW % change per selected FX pair.
    Red  = INR weaker vs that currency.
    Green = INR stronger vs that currency.
    """
    PAIR_LABELS = {
        'usdinr': 'USD/INR',
        'eurinr': 'EUR/INR',
        'gbpinr': 'GBP/INR',
        'jpyinr': 'JPY/INR',
        'cnhinr': 'CNH/INR',
    }
    ORDER = ['usdinr', 'eurinr', 'gbpinr', 'jpyinr', 'cnhinr']

    rows = [
        (PAIR_LABELS[p], data.get(f'{p}_close', 'N/A'), data.get(f'{p}_wow_val', 0))
        for p in ORDER
        if p in selected_fx_pairs and not data.get(f'{p}_excluded')
    ]

    if not rows:
        return ('<svg viewBox="0 0 480 40" xmlns="http://www.w3.org/2000/svg" '
                'style="width:100%;display:block;">'
                '<text x="240" y="24" text-anchor="middle" font-family="Arial" '
                'font-size="11" fill="#aaa">No FX pairs selected</text></svg>')

    max_abs  = max(abs(r[2]) for r in rows) or 0.5
    n        = len(rows)
    row_h    = 30
    label_w  = 62     # left label column
    center_x = label_w + 20   # zero-line x
    max_bar  = 200    # px for max abs move
    svg_w    = center_x + max_bar + 60
    svg_h    = n * row_h + 24

    bars_svg = ''
    for i, (name, close, val) in enumerate(rows):
        y     = 20 + i * row_h
        color = '#c0392b' if val > 0 else '#1a7a1a'
        bw    = abs(val) / max_abs * max_bar if max_abs else 2
        bx    = center_x if val >= 0 else center_x - bw
        sign  = '+' if val > 0 else ''

        label_anchor = 'end'
        val_x  = center_x + bw + 5 if val >= 0 else center_x - bw - 4
        val_anc = 'start' if val >= 0 else 'end'

        bars_svg += f'''
  <text x="{label_w}" y="{y + 14}" text-anchor="end"
        font-family="Arial" font-size="9.5" fill="#333">{name}</text>
  <text x="{label_w + 2}" y="{y + 22}" text-anchor="start"
        font-family="Arial" font-size="7.5" fill="#aaa">{close}</text>
  <rect x="{bx:.1f}" y="{y + 2}" width="{max(bw, 1.5):.1f}" height="16"
        fill="{color}" opacity=".72" rx="2"/>
  <text x="{val_x:.1f}" y="{y + 14}" text-anchor="{val_anc}"
        font-family="Arial" font-size="9" fill="{color}" font-weight="bold"
        >{sign}{val:.2f}%</text>'''

    zero_line = (f'<line x1="{center_x}" y1="16" x2="{center_x}" y2="{svg_h - 6}" '
                 f'stroke="#d8dde3" stroke-width="1"/>')

    header = (f'<text x="{center_x}" y="13" text-anchor="middle" '
              f'font-family="Arial" font-size="7.5" fill="#9aabb8">'
              f'← INR stronger &nbsp;&nbsp; INR weaker →</text>')

    return (f'<svg viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg" '
            f'style="width:100%;max-width:{svg_w}px;display:block;">\n'
            f'  {header}\n  {zero_line}\n  {bars_svg}\n</svg>')

# ── SVG: Brent 5-day chart (no USD/INR overlay) ───────────────────────────────

X5 = [70, 180, 290, 380, 460]

def _clamp(y, top, bottom):
    return max(top + 1, min(bottom - 1, y))

def _y(val, val_min, val_max, y_bottom, y_top):
    r = val_max - val_min if val_max != val_min else 0.001
    return _clamp(y_bottom - ((val - val_min) / r) * (y_bottom - y_top), y_top, y_bottom)

def _pts(values, x_pos, vmin, vmax, yb, yt):
    last = next((v for v in values if v is not None), (vmin + vmax) / 2)
    pts = []
    for x, v in zip(x_pos, values):
        if v is not None:
            last = v
        pts.append(f'{x},{_y(last, vmin, vmax, yb, yt):.0f}')
    return ' '.join(pts)

def _dots(values, x_pos, vmin, vmax, yb, yt, color):
    last = next((v for v in values if v is not None), (vmin + vmax) / 2)
    out = []
    for x, v in zip(x_pos, values):
        if v is not None:
            last = v
        out.append(f'<circle cx="{x}" cy="{_y(last, vmin, vmax, yb, yt):.0f}" '
                   f'r="3" fill="{color}"/>')
    return '\n    '.join(out)

def build_brent_chart(brent_5d, day_labels):
    b_clean = [v for v in brent_5d if v is not None]
    if not b_clean:
        return ('<svg viewBox="0 0 520 80" xmlns="http://www.w3.org/2000/svg" '
                'style="width:100%;display:block;">'
                '<text x="260" y="40" text-anchor="middle" font-family="Arial" '
                'font-size="11" fill="#aaa">Brent chart unavailable</text></svg>')

    bmin, bmax = min(b_clean) * 0.995, max(b_clean) * 1.005
    YB, YT = 62, 12
    pts  = _pts(brent_5d, X5, bmin, bmax, YB, YT)
    dots = _dots(brent_5d, X5, bmin, bmax, YB, YT, '#c0392b')

    day_svg = ''.join(
        f'<text x="{x}" y="76" text-anchor="middle" font-family="Arial" '
        f'font-size="8" fill="#8a9aaa">{lbl}</text>\n    '
        for x, lbl in zip(X5, day_labels)
    )

    return f'''<svg viewBox="0 0 520 82" xmlns="http://www.w3.org/2000/svg" style="width:100%;display:block;">
    <line x1="50" y1="{YT}" x2="490" y2="{YT}" stroke="#f0e0e0" stroke-width="1"/>
    <line x1="50" y1="{YB}" x2="490" y2="{YB}" stroke="#f0e0e0" stroke-width="1"/>
    <text x="48" y="{YT+3}" text-anchor="end" font-family="Arial" font-size="8" fill="#c0392b">${bmax:.0f}</text>
    <text x="48" y="{YB+3}" text-anchor="end" font-family="Arial" font-size="8" fill="#c0392b">${bmin:.0f}</text>
    {day_svg}
    <polyline points="{pts}" fill="none" stroke="#c0392b" stroke-width="2.5"/>
    {dots}
    <rect x="50" y="4" width="8" height="3" fill="#c0392b"/>
    <text x="61" y="9" font-family="Arial" font-size="8" fill="#444">Brent crude ($/bbl)</text>
</svg>'''

# ── Range bar ──────────────────────────────────────────────────────────────────

def range_bar(pct, color='#666'):
    return (f'<div class="rbar-track">'
            f'<div class="rbar-dot" style="left:{pct:.0f}%;background:{color};"></div>'
            f'</div>')

# ── Story card ─────────────────────────────────────────────────────────────────

COLOR_CLASS = {'red': 'story red-s', 'amber': 'story amber', 'blue': 'story blue-s'}

def story_card(story):
    cls       = COLOR_CLASS.get(story.get('color', 'blue'), 'story blue-s')
    links_html = ' &nbsp;·&nbsp; '.join(
        f'<a href="{lnk.get("url","#")}" target="_blank">{lnk.get("text","→ Source")}</a>'
        for lnk in story.get('links', [])
    )
    return f'''<div class="{cls}">
  <div class="story-tag">{story.get("tag","")}</div>
  <div class="story-head">{story.get("headline","")}</div>
  <div class="story-body">{story.get("body","")}</div>
  <div class="story-imp">{story.get("inr_relevance","")}</div>
  {'<div class="story-link">' + links_html + '</div>' if links_html else ''}
</div>'''

def cal_row(event):
    impact  = event.get('impact', 'MED')
    tag_cls = 'tag-hi' if impact == 'HIGH' else 'tag-med'
    row_cls = ' class="hi-row"' if impact == 'HIGH' else ''
    return (f'<tr{row_cls}>'
            f'<td class="dt">{event.get("date","")}</td>'
            f'<td><span class="{tag_cls}">{impact}</span>&nbsp; {event.get("event","")} '
            f'&nbsp;<a href="{event.get("url","#")}" target="_blank" '
            f'style="font-size:9px;color:#1a5fa8;">→ Source</a></td></tr>')

# ── Base CSS ───────────────────────────────────────────────────────────────────

BASE_CSS = """
*{margin:0;padding:0;box-sizing:border-box;}
body{background:#f0f2f5;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1a1a2e;-webkit-text-size-adjust:100%;}
.wrap{max-width:620px;margin:0 auto;background:#fff;}
.hdr{background:#002060;padding:14px 16px 12px;border-bottom:3px solid #c8a84b;}
.hdr-brand{font-size:9px;letter-spacing:.16em;color:#7a9abf;text-transform:uppercase;margin-bottom:4px;}
.hdr-top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;}
.hdr-title{font-size:20px;font-weight:700;color:#fff;line-height:1.1;}
.hdr-week{font-size:10px;color:#c8a84b;font-weight:700;margin-top:3px;letter-spacing:.06em;}
.hdr-sub{font-size:9px;color:#5a7a9a;margin-top:2px;}
.hdr-date{text-align:right;font-size:9.5px;color:#8aaac8;line-height:1.7;flex-shrink:0;}
.mood{display:inline-block;background:#7d1c1c;color:#ffb3b3;font-size:9px;font-weight:700;letter-spacing:.1em;padding:2px 8px;margin-top:7px;text-transform:uppercase;}
.theme{background:#f7f4ed;border-bottom:2px solid #c8a84b;padding:7px 16px;font-size:10.5px;color:#3a2800;line-height:1.5;}
.theme strong{color:#002060;}
.sec-hdr{padding:8px 16px;font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#fff;display:flex;align-items:center;gap:8px;}
.sec-hdr.blue{background:#002060;}.sec-hdr.teal{background:#0a5a5a;}.sec-hdr.slate{background:#2a3a4a;}
.sec-num{font-size:16px;font-weight:700;opacity:.5;}
.sub-lbl{background:#f4f6f9;border-top:1px solid #dde1e8;border-bottom:1px solid #dde1e8;padding:4px 16px;font-size:9px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#5a6a80;border-left:3px solid #c8a84b;}
.row{display:flex;gap:0;}
.card{flex:1;padding:10px 14px;border:1px solid #eef0f3;background:#fff;}
.card+.card{border-left:none;}
.lbl{font-size:9px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#6a7a8a;margin-bottom:3px;}
.val{font-size:21px;font-weight:700;color:#1a1a2e;line-height:1;}
.val-md{font-size:16px;font-weight:700;color:#1a1a2e;line-height:1;}
.chg{font-size:11px;font-weight:600;margin-top:3px;}
.red{color:#c0392b;}.green{color:#1a7a1a;}.grey{color:#7a8a9a;}
.sub{font-size:10px;color:#6a7a8a;margin-top:4px;line-height:1.4;}
.src-line{font-size:8px;color:#b0c0ce;margin-top:5px;}
.src-line a{color:#1a5fa8;text-decoration:none;}
.rbar{margin-top:7px;}
.rbar-lbl{font-size:8px;color:#9aabb8;display:flex;justify-content:space-between;}
.rbar-track{background:#e8eef3;height:4px;border-radius:2px;position:relative;margin-top:3px;}
.rbar-dot{position:absolute;top:-3px;width:10px;height:10px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px #888;transform:translateX(-5px);}
.insight{background:#f0f4fa;border-left:3px solid #002060;padding:8px 14px;font-size:10.5px;color:#1a1a2e;line-height:1.5;}
.insight strong{color:#002060;}
.chart-wrap{padding:10px 14px;border:1px solid #eef0f3;border-top:none;background:#fff;}
.chart-title{font-size:9px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#5a6a80;margin-bottom:6px;}
.story{padding:11px 14px;border:1px solid #eef0f3;border-left:3px solid #002060;background:#fff;}
.story+.story{border-top:none;}
.story.amber{border-left-color:#d4750a;}.story.red-s{border-left-color:#c0392b;}.story.blue-s{border-left-color:#1a5fa8;}
.story-tag{font-size:8.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#8a9aaa;margin-bottom:4px;}
.story-head{font-size:13px;font-weight:700;color:#1a1a2e;margin-bottom:5px;line-height:1.3;}
.story-body{font-size:11px;color:#3a4a5a;line-height:1.55;}
.story-imp{font-size:10.5px;font-weight:700;color:#002060;margin-top:6px;padding:4px 8px;background:#eef2f9;border-radius:2px;line-height:1.4;}
.story-link{font-size:9.5px;margin-top:5px;} .story-link a{color:#1a5fa8;text-decoration:none;font-weight:700;}
.cal{width:100%;border-collapse:collapse;font-size:11px;}
.cal td{padding:6px 12px;border-bottom:1px solid #eef0f3;vertical-align:top;}
.cal .dt{font-size:9px;font-weight:700;color:#8a9aaa;white-space:nowrap;width:60px;}
.cal .hi-row{background:#fdf4f4;}
.tag-hi{display:inline-block;padding:1px 5px;border-radius:2px;font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;background:#fbe0e0;color:#c0392b;}
.tag-med{display:inline-block;padding:1px 5px;border-radius:2px;font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;background:#fef3dc;color:#b07000;}
.ftr{background:#f4f6f9;border-top:2px solid #002060;padding:9px 16px;font-size:8.5px;color:#6a7a8a;line-height:1.7;}
.ftr a{color:#1a5fa8;text-decoration:none;font-weight:700;}
@media(max-width:460px){.row{flex-direction:column;}.card+.card{border-left:1px solid #eef0f3;border-top:none;}.hdr-date{display:none;}.val{font-size:18px;}}
"""

# ── Weekly HTML generator ─────────────────────────────────────────────────────

def generate_weekly_html(data, stories, week_ahead_events, commentary=None,
                         selected_sections=None):
    """
    Generate the full weekly snapshot HTML.

    selected_sections: {
        'fx_pairs': ['usdinr', 'eurinr', ...],  # subset
        'rates':  True,
        'oil':    True,
        'gold':   True,
        'macro':  True,
    }
    Defaults to all sections if None.
    """
    d   = data
    c   = commentary or {}
    sec = selected_sections or {
        'fx_pairs': ['usdinr', 'eurinr', 'gbpinr', 'jpyinr', 'cnhinr'],
        'rates': True, 'oil': True, 'gold': True, 'macro': True,
    }

    def ai(key, fallback=''):
        return c.get(key, fallback) or fallback

    fx_pairs      = sec.get('fx_pairs', [])
    show_rates    = sec.get('rates', True)
    show_oil      = sec.get('oil', True)
    show_gold     = sec.get('gold', True)
    show_macro    = sec.get('macro', True)
    show_currency = bool(fx_pairs)

    # ── Derived values ──
    mood_tag   = ai('mood_tag', 'WEEKLY SNAPSHOT · BLOOMBERG FX + AI DATA')
    theme_html = ''
    theme_text = ai('theme', '')
    if theme_text:
        theme_html = (f'<div class="theme"><strong>Week in one line:</strong> {theme_text}</div>')

    inr_insight  = ai('inr_insight', d.get('inr_insight', ''))
    usdinr_wow_v = d.get('usdinr_wow_val', 0)
    usd_wow_color = '#c0392b' if usdinr_wow_v > 0 else '#666'

    # Per-pair sub-commentary
    def pair_sub(pair, fallback=''):
        return ai(f'{pair}_sub', fallback)

    # ── Section number counter ──
    sec_n = [0]
    def next_sec(label, cls='blue'):
        sec_n[0] += 1
        return (f'<div class="sec-hdr {cls}">'
                f'<span class="sec-num">0{sec_n[0]}</span> {label}</div>')

    # ── Build sections ──
    html_sections = []

    # — Section: Currency —
    if show_currency:
        currency_html = next_sec('CURRENCY', 'blue')

        # 1.1 USD/INR + DXY
        if 'usdinr' in fx_pairs or True:  # DXY always shown in currency section
            usdinr_card = ''
            if 'usdinr' in fx_pairs:
                usdinr_sub = pair_sub('usdinr',
                    f'Open: {d.get("usdinr_open","N/A")} · RBI Ref: {d.get("rbi_ref","N/A")} · '
                    f'Source: Bloomberg')
                usdinr_card = f'''<div class="card">
    <div class="lbl">USD / INR — Week Close</div>
    <div class="val">{d.get("usdinr_close","N/A")}</div>
    <div class="chg">{d.get("usdinr_wow","N/A")}</div>
    <div class="sub">{usdinr_sub}</div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo {d.get("usdinr_52w_lo","N/A")}</span>
      <span>52W Hi {d.get("usdinr_52w_hi","N/A")}</span></div>
      {range_bar(d.get("usdinr_52w_pct",50), usd_wow_color)}
    </div>
    <div class="src-line">Bloomberg · <a href="https://www.rbi.org.in" target="_blank">RBI</a></div>
  </div>'''

            dxy_sub  = ai('dxy_sub', '')
            dxy_card = f'''<div class="card">
    <div class="lbl">DXY — Dollar Index</div>
    <div class="val">{d.get("dxy_close","N/A")}</div>
    <div class="chg">{d.get("dxy_wow","N/A")}</div>
    <div class="sub">{dxy_sub}</div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo {d.get("dxy_52w_lo","N/A")}</span>
      <span>52W Hi {d.get("dxy_52w_hi","N/A")}</span></div>
      {range_bar(d.get("dxy_52w_pct",50), "#666")}
    </div>
    <div class="src-line"><a href="https://www.investing.com/indices/usdollar" target="_blank">Investing.com DXY</a> · Gemini AI</div>
  </div>'''

            currency_html += (
                f'<div class="sub-lbl">1.1 INR Spot &amp; Dollar Index</div>'
                f'<div class="row">{usdinr_card}{dxy_card}</div>'
            )

        # INR insight + WoW bar chart
        inr_chart = build_inr_change_chart(d, fx_pairs)
        currency_html += (
            f'<div class="insight"><strong>Key read:</strong> {inr_insight}</div>'
            f'<div class="chart-wrap" style="border-top:1px solid #eef0f3;">'
            f'  <div class="chart-title">INR WoW % change — Bloomberg open→close '
            f'(negative = INR stronger)</div>'
            f'  {inr_chart}'
            f'  <div class="src-line">Bloomberg terminal data</div>'
            f'</div>'
        )

        # 1.2 G3 pairs (in rows of 2)
        g3_pairs = [p for p in ['eurinr', 'gbpinr', 'jpyinr', 'cnhinr']
                    if p in fx_pairs and not d.get(f'{p}_excluded')]
        if g3_pairs:
            LABELS = {'eurinr': 'EUR / INR', 'gbpinr': 'GBP / INR',
                      'jpyinr': 'JPY / INR (per 100 JPY)', 'cnhinr': 'CNH / INR'}
            currency_html += '<div class="sub-lbl">1.2 G3 vs INR — Week Close &amp; WoW</div>'
            # Group into rows of 2
            for i in range(0, len(g3_pairs), 2):
                chunk = g3_pairs[i:i+2]
                row_html = ''
                for p in chunk:
                    sub_txt = pair_sub(p, '')
                    wow_c   = '#c0392b' if d.get(f'{p}_wow_val', 0) > 0 else '#666'
                    row_html += f'''<div class="card">
    <div class="lbl">{LABELS[p]}</div>
    <div class="val-md">{d.get(f"{p}_close","N/A")}</div>
    <div class="chg">{d.get(f"{p}_wow","N/A")}</div>
    <div class="sub">{sub_txt}</div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo {d.get(f"{p}_52w_lo","N/A")}</span>
      <span>Hi {d.get(f"{p}_52w_hi","N/A")}</span></div>
      {range_bar(d.get(f"{p}_52w_pct",50), wow_c)}
    </div>
    <div class="src-line">Bloomberg terminal data</div>
  </div>'''
                # Pad with empty card if odd number
                if len(chunk) == 1:
                    row_html += '<div class="card" style="background:#fafbfc;"></div>'
                currency_html += f'<div class="row">{row_html}</div>'

        html_sections.append(currency_html)

    # — Section: Rates & Yields —
    if show_rates:
        rates_html = next_sec('RATES &amp; POLICY', 'teal')
        rates_html += '<div class="sub-lbl">2.1 Bond Yields</div>'

        us10y_sub = ai('us10y_sub', '')
        in10y_sub = ai('in10y_sub', f'India–US spread: {d.get("yield_spread","N/A")}')
        if d.get('yield_spread', 'N/A') != 'N/A' and 'spread' not in in10y_sub.lower():
            in10y_sub += f'<br>India–US spread: <strong>{d.get("yield_spread","N/A")}</strong>'

        rates_html += f'''<div class="row">
  <div class="card">
    <div class="lbl">US 10Y Treasury</div>
    <div class="val">{d.get("us10y_close","N/A")}%</div>
    <div class="chg">{d.get("us10y_wow","N/A")}</div>
    <div class="sub">{us10y_sub}</div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo {d.get("us10y_52w_lo","N/A")}%</span>
      <span>Hi {d.get("us10y_52w_hi","N/A")}%</span></div>
      {range_bar(d.get("us10y_52w_pct",50), "#c0392b" if d.get("us10y_wow_val",0)>0 else "#666")}
    </div>
    <div class="src-line"><a href="https://fred.stlouisfed.org/series/DGS10" target="_blank">FRED DGS10</a> · Gemini AI</div>
  </div>
  <div class="card">
    <div class="lbl">India 10Y G-Sec (CCIL)</div>
    <div class="val">{d.get("in10y_close","N/A")}%</div>
    <div class="chg">{d.get("in10y_wow","N/A")}</div>
    <div class="sub">{in10y_sub}</div>
    <div class="rbar">
      <div class="rbar-lbl"><span>52W Lo {d.get("in10y_52w_lo","N/A")}%</span>
      <span>Hi {d.get("in10y_52w_hi","N/A")}%</span></div>
      {range_bar(d.get("in10y_52w_pct",50), "#c0392b" if d.get("in10y_wow_val",0)>0 else "#666")}
    </div>
    <div class="src-line"><a href="https://www.ccilindia.com" target="_blank">CCIL</a> · Gemini AI (verify before distributing)</div>
  </div>
</div>'''

        fed_sub = ai('fed_sub', '■ On hold')
        rbi_sub = ai('rbi_sub', '■ On hold · Neutral stance')
        rates_html += f'''<div class="sub-lbl">2.2 Policy Rates</div>
<div class="row">
  <div class="card">
    <div class="lbl">Fed Funds Rate</div>
    <div class="val" style="font-size:17px;">{d.get("fed_rate","N/A")}</div>
    <div class="chg grey">■ On hold</div>
    <div class="sub">{fed_sub}</div>
    <div class="src-line"><a href="https://www.federalreserve.gov/monetarypolicy/openmarket.htm" target="_blank">Fed Reserve</a> · Gemini AI</div>
  </div>
  <div class="card">
    <div class="lbl">RBI Repo Rate</div>
    <div class="val" style="font-size:17px;">{d.get("rbi_rate","N/A")}</div>
    <div class="chg grey">■ On hold · Neutral stance</div>
    <div class="sub">{rbi_sub}</div>
    <div class="src-line"><a href="https://www.rbi.org.in" target="_blank">RBI MPC</a> · Gemini AI</div>
  </div>
</div>'''
        html_sections.append(rates_html)

    # — Section: Commodities —
    if show_oil or show_gold:
        comm_html = next_sec('COMMODITIES', 'slate')
        comm_html += '<div class="sub-lbl">Commodities — Week Close &amp; WoW</div>'
        comm_row  = ''

        if show_oil:
            brent_sub = ai('brent_sub', f'Week high: ${d.get("brent_wk_high","N/A")}')
            comm_row += f'''<div class="card">
    <div class="lbl">Brent Crude ($/bbl)</div>
    <div class="val">${d.get("brent_close","N/A")}</div>
    <div class="chg">{d.get("brent_wow","N/A")}</div>
    <div class="sub">{brent_sub}</div>
    <div class="src-line"><a href="https://tradingeconomics.com/commodity/brent-crude-oil" target="_blank">TradingEconomics</a> · Gemini AI</div>
  </div>'''

        if show_gold:
            gold_sub = ai('gold_sub', 'XAU/USD spot · international price')
            comm_row += f'''<div class="card">
    <div class="lbl">Gold — XAU/USD</div>
    <div class="val-md">{d.get("gold_usd","N/A")}</div>
    <div class="chg">{d.get("gold_wow","N/A")}</div>
    <div class="sub">{gold_sub}</div>
    <div class="src-line"><a href="https://finance.yahoo.com/quote/GC=F/" target="_blank">Yahoo Finance GC=F</a> · Gemini AI</div>
  </div>'''

        # Pad if only one shown
        if show_oil != show_gold:
            comm_row += '<div class="card" style="background:#fafbfc;"></div>'

        comm_html += f'<div class="row">{comm_row}</div>'

        if show_oil and any(d.get('brent_5d', [])):
            brent_chart = build_brent_chart(
                d.get('brent_5d', [None]*5),
                d.get('day_labels', ['Mon','Tue','Wed','Thu','Fri'])
            )
            comm_html += (
                f'<div class="chart-wrap">'
                f'<div class="chart-title">Brent crude — 5-day (yfinance indicative)</div>'
                f'{brent_chart}'
                f'<div class="src-line"><a href="https://finance.yahoo.com/quote/BZ=F/" '
                f'target="_blank">Yahoo Finance BZ=F</a></div></div>'
            )

        html_sections.append(comm_html)

    # — Section: Macro —
    if show_macro:
        stories_html = '\n'.join(story_card(s) for s in stories)

        week_ahead_section = ''
        if week_ahead_events:
            cal_rows = '\n'.join(cal_row(e) for e in week_ahead_events)
            week_ahead_section = f'''<div class="sub-lbl">3.2 Week Ahead</div>
<div style="border:1px solid #eef0f3;">
  <table class="cal">{cal_rows}</table>
</div>'''

        macro_html = (
            next_sec('MACRO', 'slate') +
            '<div class="sub-lbl">3.1 Big Stories This Week</div>' +
            stories_html +
            week_ahead_section
        )
        html_sections.append(macro_html)

    # ── Assemble ──
    body = '\n'.join(html_sections)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StanC FM · Weekly · W{d.get("week_num","")} {d.get("year","")}</title>
<style>{BASE_CSS}</style>
</head>
<body>
<div class="wrap">

<div class="hdr">
  <div class="hdr-brand">Standard Chartered · Financial Markets Sales · India Desk</div>
  <div class="hdr-top">
    <div>
      <div class="hdr-title">Global FX — Weekly</div>
      <div class="hdr-week">WEEK {d.get("week_num","")} · {d.get("week_start","").upper()} – {d.get("week_end","").upper()}</div>
      <div class="hdr-sub">Internal &amp; Client Briefing · India FM Sales</div>
      <div class="mood">{mood_tag}</div>
    </div>
    <div class="hdr-date">Generated {d.get("generated_at","")}</div>
  </div>
</div>

{theme_html}

{body}

<div class="ftr">
  <strong>Standard Chartered Financial Markets — India FM Sales Desk</strong><br>
  Week {d.get("week_num","")} · {d.get("week_start","")} – {d.get("week_end","")} · Generated {d.get("generated_at","")}<br>
  FX pairs: Bloomberg terminal · DXY / Yields / Brent / Gold: Gemini AI + Google Search (verify before distributing)<br>
  <span style="color:#c0392b;">⚠ India 10Y yield is Gemini-estimated — verify against CCIL/FIMMDA before client distribution.</span>
</div>

</div>
</body>
</html>'''

# ── JPEG generation via WeasyPrint ────────────────────────────────────────────

def html_to_jpeg(html_string):
    """
    Render HTML to JPEG.
    Pipeline: WeasyPrint → PDF → PyMuPDF → PNG → Pillow → JPEG.
    write_png() was removed in WeasyPrint 53+; write_pdf() is the stable output path.
    Returns (jpeg_bytes, error_or_None).
    """
    try:
        from weasyprint import HTML, CSS
        import fitz          # PyMuPDF — converts PDF page to raster
        from PIL import Image
        import io

        # Force a single tall page so the full snapshot fits without pagination
        page_css = CSS(string='@page { size: 660px 3200px; margin: 0; } '
                               'body { max-width: 660px; }')
        pdf_bytes = HTML(string=html_string).write_pdf(stylesheets=[page_css])

        # Rasterise first PDF page at 2× scale for crisp output
        pdf_doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        page    = pdf_doc[0]
        mat     = fitz.Matrix(2, 2)
        pix     = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes('png')
        pdf_doc.close()

        # Convert to JPEG, crop trailing whitespace
        img  = Image.open(io.BytesIO(png_bytes)).convert('RGB')
        bbox = img.getbbox()
        if bbox:
            img = img.crop((0, 0, img.width, min(bbox[3] + 30, img.height)))

        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=92)
        return buf.getvalue(), None

    except ImportError as e:
        return None, (f'Missing library: {e}. '
                      'Ensure weasyprint, PyMuPDF, and Pillow are in requirements.txt.')
    except Exception as e:
        return None, f'JPEG render error: {e}'
