# snapshot_page.py  v4
#
# 3-step pipeline:
#   Step 1 — CONFIG   : section checkboxes + Bloomberg FX inputs + week dates
#   Step 2 — REVIEW   : AI-fetched market data (editable) + generate button
#   Step 3 — PREVIEW  : HTML preview + Download HTML + Download JPEG

import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, date, timedelta
import time


# ── API key helper ─────────────────────────────────────────────────────────────

def _get_api_key():
    try:
        return st.secrets['GEMINI_API_KEY']
    except Exception:
        return st.session_state.get('gemini_key', '')


# ── Session state initialiser ──────────────────────────────────────────────────

def _init_state():
    ss = st.session_state
    ss.setdefault('pipeline_step', 'config')
    ss.setdefault('selected_fx_pairs',
                  ['usdinr', 'eurinr', 'gbpinr', 'jpyinr', 'cnhinr'])
    ss.setdefault('show_rates', True)
    ss.setdefault('show_oil',   True)
    ss.setdefault('show_gold',  True)
    ss.setdefault('show_macro', True)
    ss.setdefault('fx_inputs',  {})
    ss.setdefault('ai_raw_data', {})
    ss.setdefault('review_initialised', False)
    ss.setdefault('html_output', None)
    ss.setdefault('jpeg_bytes',  None)
    ss.setdefault('week_start_dt', None)
    ss.setdefault('week_end_dt',   None)


# ── Shared header ──────────────────────────────────────────────────────────────

def _render_header():
    st.markdown("""
<style>
.snap-header{background:#000;border-bottom:2px solid #c8a84b;
  padding:8px 12px;display:flex;align-items:center;justify-content:space-between;margin-bottom:0;}
.snap-title{font-size:13px;font-weight:700;color:#e8e8e8;letter-spacing:.08em;}
.snap-sub{font-size:9px;color:#3a3a3a;letter-spacing:.05em;}
.snap-warn{background:#0a0800;border:1px solid #3a2800;border-radius:3px;
  padding:6px 10px;font-size:10px;color:#c8a84b;margin-top:8px;}
.err-box{background:#1a0000;border:1px solid #5a1a1a;border-radius:3px;
  padding:6px 10px;font-size:10px;color:#ff8888;margin-top:4px;
  font-family:monospace;white-space:pre-wrap;word-break:break-all;}
.step-badge{font-size:9px;font-weight:700;color:#3a3a3a;letter-spacing:.12em;
  padding-bottom:6px;border-bottom:1px solid #181818;margin-bottom:10px;}
</style>
<div class="snap-header">
  <div>
    <span class="snap-title">📊 FX SNAPSHOT GENERATOR</span>
    <span class="snap-sub">&nbsp;·&nbsp; WEEKLY · BLOOMBERG FX + GEMINI AI</span>
  </div>
  <div style="font-size:9px;color:#3a3a3a;font-family:monospace;">
    BLOOMBERG FX · GEMINI 2.5-FLASH + 3.1-FLASH-LITE
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — CONFIG
# ─────────────────────────────────────────────────────────────────────────────

def _step_config(api_key):
    ss = st.session_state
    st.markdown('<div class="step-badge">STEP 1 OF 3 &nbsp;·&nbsp; CONFIGURE & ENTER BLOOMBERG DATA</div>',
                unsafe_allow_html=True)

    # ── Week dates ──
    st.markdown('#### 📅 Week dates')
    mon_def, fri_def = _default_week()
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        w_start = st.date_input('Week start (Monday)', value=mon_def, key='week_start_input')
    with col_d2:
        w_end = st.date_input('Week end (Friday)', value=fri_def, key='week_end_input')

    if w_start >= w_end:
        st.warning('Week start must be before week end.')
        return

    st.divider()

    # ── Output section selector ──
    st.markdown('#### 📋 Select output sections')
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.markdown('**FX Pairs**')
        usdinr_on = st.checkbox('USD/INR',  value='usdinr' in ss.selected_fx_pairs, key='cb_usdinr')
        eurinr_on = st.checkbox('EUR/INR',  value='eurinr' in ss.selected_fx_pairs, key='cb_eurinr')
        gbpinr_on = st.checkbox('GBP/INR',  value='gbpinr' in ss.selected_fx_pairs, key='cb_gbpinr')
        jpyinr_on = st.checkbox('JPY/INR',  value='jpyinr' in ss.selected_fx_pairs, key='cb_jpyinr')
        cnhinr_on = st.checkbox('CNH/INR',  value='cnhinr' in ss.selected_fx_pairs, key='cb_cnhinr')
    with col_b:
        st.markdown('**Rates & Yields**')
        rates_on = st.checkbox('US 10Y + India 10Y + Policy rates',
                               value=ss.show_rates, key='cb_rates')
    with col_c:
        st.markdown('**Commodities**')
        oil_on  = st.checkbox('Oil (Brent)',    value=ss.show_oil,  key='cb_oil')
        gold_on = st.checkbox('Gold (XAU/USD)', value=ss.show_gold, key='cb_gold')
    with col_d:
        st.markdown('**Macro**')
        macro_on = st.checkbox('Macro stories + week ahead',
                               value=ss.show_macro, key='cb_macro')

    selected_fx = [p for p, on in [('usdinr', usdinr_on), ('eurinr', eurinr_on),
                                    ('gbpinr', gbpinr_on), ('jpyinr', jpyinr_on),
                                    ('cnhinr', cnhinr_on)] if on]
    if not selected_fx and not rates_on and not oil_on and not gold_on and not macro_on:
        st.error('Please select at least one output section.')
        return

    st.divider()

    # ── Bloomberg FX inputs ──
    PAIR_LABELS = {
        'usdinr': 'USD/INR',
        'eurinr': 'EUR/INR',
        'gbpinr': 'GBP/INR',
        'jpyinr': 'JPY/INR (per 100 JPY)',
        'cnhinr': 'CNH/INR',
    }
    DEFAULT_OPENS = {
        'usdinr': 84.20, 'eurinr': 91.50, 'gbpinr': 107.00,
        'jpyinr': 56.00, 'cnhinr': 11.55,
    }
    DEFAULT_CLOSES = {
        'usdinr': 84.20, 'eurinr': 91.50, 'gbpinr': 107.00,
        'jpyinr': 56.00, 'cnhinr': 11.55,
    }

    if selected_fx:
        st.markdown('#### 📊 Bloomberg FX data — week open &amp; close')
        st.caption('Enter Bloomberg terminal rates. App calculates WoW % change automatically.')

        hc1, hc2, hc3, hc4 = st.columns([2.5, 2, 2, 1.5])
        hc1.markdown('**Pair**')
        hc2.markdown('**Mon Open**')
        hc3.markdown('**Fri Close**')
        hc4.markdown('**WoW %**')

        fx_inputs = {}
        for pair in selected_fx:
            prev_inp = ss.fx_inputs.get(pair, {})
            lbl      = PAIR_LABELS[pair]
            c1, c2, c3, c4 = st.columns([2.5, 2, 2, 1.5])
            c1.markdown(f'`{lbl}`')
            open_val  = c2.number_input('Open',  value=float(prev_inp.get('open',  DEFAULT_OPENS[pair])),
                                        format='%.2f', step=0.01,
                                        key=f'fx_open_{pair}', label_visibility='collapsed')
            close_val = c3.number_input('Close', value=float(prev_inp.get('close', DEFAULT_CLOSES[pair])),
                                        format='%.2f', step=0.01,
                                        key=f'fx_close_{pair}', label_visibility='collapsed')
            wow_val   = ((close_val - open_val) / open_val * 100) if open_val else 0
            wow_color = 'red' if wow_val > 0 else ('green' if wow_val < 0 else 'grey')
            c4.markdown(f'<span style="color:{"#c0392b" if wow_val>0 else "#1a7a1a" if wow_val<0 else "#999"};'
                        f'font-weight:700;">{wow_val:+.2f}%</span>', unsafe_allow_html=True)
            fx_inputs[pair] = {'open': open_val, 'close': close_val}
    else:
        fx_inputs = {}

    st.divider()

    # ── Fetch button ──
    st.markdown('#### 🔍 Fetch AI market data')
    st.caption('Gemini 3.1-flash-lite will search for DXY, yields, Brent, Gold, Fed & RBI rates. '
               'You can review and edit all values before generating.')

    ai_fields_needed = []
    if rates_on:
        ai_fields_needed += ['US 10Y', 'India 10Y (CCIL)', 'Fed Funds', 'RBI Repo']
    ai_fields_needed.append('DXY')
    if oil_on:
        ai_fields_needed.append('Brent')
    if gold_on:
        ai_fields_needed.append('Gold XAU/USD')
    st.info(f'Will fetch: {" · ".join(ai_fields_needed)}', icon='ℹ️')

    fetch_clicked = st.button('🔍 Fetch AI Data →', type='primary', use_container_width=True)

    if fetch_clicked:
        if not api_key:
            st.error('Please enter a Gemini API key first.')
            return

        # Save current selections
        ss.selected_fx_pairs = selected_fx
        ss.show_rates  = rates_on
        ss.show_oil    = oil_on
        ss.show_gold   = gold_on
        ss.show_macro  = macro_on
        ss.fx_inputs   = fx_inputs
        ss.week_start_dt = datetime(w_start.year, w_start.month, w_start.day)
        ss.week_end_dt   = datetime(w_end.year,   w_end.month,   w_end.day)

        selected_sections_tmp = {
            'fx_pairs': selected_fx,
            'rates':    rates_on,
            'oil':      oil_on,
            'gold':     gold_on,
            'macro':    macro_on,
        }

        with st.spinner('Fetching market data via Gemini search…'):
            from macro_generator import get_ai_market_data
            week_start_str = ss.week_start_dt.strftime('%b %d, %Y')
            week_end_str   = ss.week_end_dt.strftime('%b %d, %Y')
            ai_data, err = get_ai_market_data(
                api_key, week_start_str, week_end_str, selected_sections_tmp
            )
            ss.ai_raw_data = ai_data or {}
            ss.ai_fetch_err = err

        ss.review_initialised = False   # reset so review pre-fills from new AI data
        ss.pipeline_step = 'review'
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — REVIEW
# ─────────────────────────────────────────────────────────────────────────────

def _step_review(api_key):
    ss = st.session_state
    st.markdown('<div class="step-badge">STEP 2 OF 3 &nbsp;·&nbsp; REVIEW & CONFIRM AI DATA</div>',
                unsafe_allow_html=True)

    # Back button
    if st.button('← Back to configuration'):
        ss.pipeline_step = 'config'
        st.rerun()

    # Show fetch error if any
    if ss.get('ai_fetch_err'):
        st.markdown(f'<div class="err-box">⚠ AI fetch warning: {ss.ai_fetch_err}</div>',
                    unsafe_allow_html=True)

    raw = ss.ai_raw_data

    # Pre-fill session state keys from AI data on first load
    if not ss.review_initialised:
        defaults = {
            'rev_dxy_close':    raw.get('dxy_close',    101.0),
            'rev_dxy_wow':      raw.get('dxy_wow_val',   0.0),
            'rev_us10y_close':  raw.get('us10y_close',   4.5),
            'rev_us10y_wow':    raw.get('us10y_wow_val',  0.0),
            'rev_in10y_close':  raw.get('in10y_close',   6.8),
            'rev_in10y_wow':    raw.get('in10y_wow_val',  0.0),
            'rev_brent_close':  raw.get('brent_close',   70.0),
            'rev_brent_wow':    raw.get('brent_wow_val',  0.0),
            'rev_gold_usd':     raw.get('gold_usd',    3200.0),
            'rev_gold_wow':     raw.get('gold_wow_val',   0.0),
            'rev_fed_rate':     raw.get('fed_rate',   '4.25-4.50%'),
            'rev_rbi_rate':     raw.get('rbi_rate',    '6.00%'),
        }
        for k, v in defaults.items():
            if k not in ss or not ss.review_initialised:
                ss[k] = v
        ss.review_initialised = True

    st.markdown('**Edit any value before generating. All fields are pre-filled from Gemini search.**')
    st.caption('⚠ India 10Y is Gemini-estimated — verify against CCIL/FIMMDA before client distribution.')

    # ── DXY ──
    st.markdown('---')
    st.markdown('**DXY — Dollar Index**')
    c1, c2 = st.columns(2)
    dxy_c   = c1.number_input('DXY close level', value=ss.get('rev_dxy_close', 101.0),
                               format='%.2f', step=0.01, key='rev_dxy_close')
    dxy_wow = c2.number_input('DXY WoW % change', value=ss.get('rev_dxy_wow', 0.0),
                               format='%.2f', step=0.01, key='rev_dxy_wow')

    # ── Yields ──
    if ss.show_rates:
        st.markdown('---')
        st.markdown('**US 10Y Treasury**')
        c1, c2 = st.columns(2)
        us10y_c   = c1.number_input('US 10Y close (%)', value=ss.get('rev_us10y_close', 4.5),
                                     format='%.2f', step=0.01, key='rev_us10y_close')
        us10y_wow = c2.number_input('US 10Y WoW change (bps)', value=ss.get('rev_us10y_wow', 0.0),
                                     format='%.1f', step=0.5, key='rev_us10y_wow')

        st.markdown('**India 10Y G-Sec (CCIL/FIMMDA)**')
        c3, c4 = st.columns(2)
        in10y_c   = c3.number_input('India 10Y close (%)', value=ss.get('rev_in10y_close', 6.8),
                                     format='%.2f', step=0.01, key='rev_in10y_close')
        in10y_wow = c4.number_input('India 10Y WoW change (bps)', value=ss.get('rev_in10y_wow', 0.0),
                                     format='%.1f', step=0.5, key='rev_in10y_wow')

        st.markdown('**Policy Rates** (text — edit if changed)')
        c5, c6 = st.columns(2)
        fed_rate = c5.text_input('Fed Funds Rate', value=ss.get('rev_fed_rate', '4.25-4.50%'),
                                  key='rev_fed_rate')
        rbi_rate = c6.text_input('RBI Repo Rate',  value=ss.get('rev_rbi_rate', '6.00%'),
                                  key='rev_rbi_rate')

    # ── Brent ──
    if ss.show_oil:
        st.markdown('---')
        st.markdown('**Brent Crude**')
        c1, c2 = st.columns(2)
        brent_c   = c1.number_input('Brent close (USD/bbl)', value=ss.get('rev_brent_close', 70.0),
                                     format='%.2f', step=0.01, key='rev_brent_close')
        brent_wow = c2.number_input('Brent WoW % change', value=ss.get('rev_brent_wow', 0.0),
                                     format='%.2f', step=0.01, key='rev_brent_wow')

    # ── Gold ──
    if ss.show_gold:
        st.markdown('---')
        st.markdown('**Gold XAU/USD**')
        c1, c2 = st.columns(2)
        gold_c   = c1.number_input('Gold close (USD/oz)', value=ss.get('rev_gold_usd', 3200.0),
                                    format='%.0f', step=1.0, key='rev_gold_usd')
        gold_wow = c2.number_input('Gold WoW % change', value=ss.get('rev_gold_wow', 0.0),
                                    format='%.2f', step=0.01, key='rev_gold_wow')

    st.markdown('---')
    generate_clicked = st.button('🏗 Generate Snapshot →', type='primary', use_container_width=True)

    if generate_clicked:
        if not api_key:
            st.error('Please enter a Gemini API key first.')
            return

        # Assemble reviewed data from session state
        reviewed_data = {
            'dxy_close':    ss.get('rev_dxy_close', 101.0),
            'dxy_wow_val':  ss.get('rev_dxy_wow',     0.0),
        }
        if ss.show_rates:
            reviewed_data.update({
                'us10y_close':   ss.get('rev_us10y_close', 4.5),
                'us10y_wow_val': ss.get('rev_us10y_wow',   0.0),
                'in10y_close':   ss.get('rev_in10y_close', 6.8),
                'in10y_wow_val': ss.get('rev_in10y_wow',   0.0),
                'fed_rate':      ss.get('rev_fed_rate', '4.25-4.50%'),
                'rbi_rate':      ss.get('rev_rbi_rate', '6.00%'),
            })
        if ss.show_oil:
            reviewed_data.update({
                'brent_close':   ss.get('rev_brent_close', 70.0),
                'brent_wow_val': ss.get('rev_brent_wow',    0.0),
            })
        if ss.show_gold:
            reviewed_data.update({
                'gold_usd':     ss.get('rev_gold_usd', 3200.0),
                'gold_wow_val': ss.get('rev_gold_wow',    0.0),
            })

        _run_generation(api_key, reviewed_data)


# ─────────────────────────────────────────────────────────────────────────────
# Generation pipeline
# ─────────────────────────────────────────────────────────────────────────────

def _run_generation(api_key, reviewed_data):
    ss = st.session_state

    selected_sections = {
        'fx_pairs': ss.selected_fx_pairs,
        'rates':    ss.show_rates,
        'oil':      ss.show_oil,
        'gold':     ss.show_gold,
        'macro':    ss.show_macro,
    }
    week_start_dt = ss.week_start_dt
    week_end_dt   = ss.week_end_dt

    try:
        from data_fetcher      import (process_bloomberg_fx, build_weekly_data,
                                        fetch_brent_5d, fetch_supplementary_52w)
        from macro_generator   import (generate_snapshot_commentary,
                                        get_weekly_stories, get_week_ahead)
        from html_generator    import generate_weekly_html, html_to_jpeg
    except ImportError as e:
        st.error(f'Missing module: {e}')
        return

    errors = []
    t_total = time.time()

    with st.status('Generating snapshot…', expanded=True) as status:

        # Step 1: Process Bloomberg FX + supplementary yfinance
        st.write('📡 **Step 1/5** — Processing Bloomberg FX + fetching 52w ranges…')
        t1 = time.time()
        try:
            fx_data = process_bloomberg_fx(ss.fx_inputs, ss.selected_fx_pairs)

            # Fetch 52w ranges from yfinance (supplementary, non-blocking)
            ranges_52w = fetch_supplementary_52w(selected_sections)

            # Fetch Brent 5-day chart series
            brent_5d = fetch_brent_5d(week_start_dt, week_end_dt) if ss.show_oil else None

            data = build_weekly_data(
                fx_data, reviewed_data,
                week_start_dt, week_end_dt,
                selected_sections,
                brent_5d=brent_5d,
                ranges_52w=ranges_52w,
            )
            st.write(f'✅ Data assembled ({round(time.time()-t1, 1)}s)')
        except Exception as e:
            st.error(f'❌ Data assembly failed: {e}')
            return

        # Step 2: Commentary (INTENSIVE tier)
        st.write('✍️ **Step 2/5** — Generating commentary (gemini-2.5-flash)…')
        t2 = time.time()
        commentary, c_err = generate_snapshot_commentary(api_key, data)
        elapsed2 = round(time.time() - t2, 1)
        if c_err:
            st.warning(f'⚠️ Commentary partial ({elapsed2}s)')
            st.markdown(f'<div class="err-box">{c_err}</div>', unsafe_allow_html=True)
            errors.append(f'Commentary: {c_err}')
            commentary = {}
        else:
            st.write(f'✅ Commentary ready — {len(commentary)} fields ({elapsed2}s)')

        # Step 3: Macro stories (INTENSIVE search → MEDIUM structure)
        stories = []
        if ss.show_macro:
            st.write('🔍 **Step 3/5** — Macro stories: searching (gemini-2.5-flash + search)…')
            t3 = time.time()
            try:
                stories, s_err = get_weekly_stories(
                    api_key,
                    data.get('week_start', ''),
                    data.get('week_end', ''),
                    data.get('week_num', ''),
                    data=data,
                )
            except Exception as e:
                s_err = str(e)
                stories = []
            elapsed3 = round(time.time() - t3, 1)
            if s_err:
                st.warning(f'⚠️ Stories partial ({elapsed3}s)')
                st.markdown(f'<div class="err-box">{s_err}</div>', unsafe_allow_html=True)
                errors.append(f'Stories: {s_err}')
            else:
                st.write(f'✅ {len(stories)} stories ready ({elapsed3}s)')
        else:
            st.write('⏭ **Step 3/5** — Macro stories skipped (not selected)')

        # Step 4: Week ahead (LIGHT tier)
        week_ahead = []
        if ss.show_macro:
            st.write('📆 **Step 4/5** — Week ahead (gemini-3.1-flash-lite)…')
            t4 = time.time()
            try:
                week_ahead, wa_err = get_week_ahead(api_key, data.get('week_end', ''))
            except Exception as e:
                wa_err = str(e)
                week_ahead = []
            elapsed4 = round(time.time() - t4, 1)
            if wa_err:
                st.write(f'⚠️ Week ahead partial ({elapsed4}s)')
                errors.append(f'Week ahead: {wa_err}')
            else:
                st.write(f'✅ {len(week_ahead)} events ({elapsed4}s)')
        else:
            st.write('⏭ **Step 4/5** — Week ahead skipped')

        # Step 5: Build HTML
        st.write('🏗 **Step 5/5** — Building HTML…')
        t5 = time.time()
        try:
            html = generate_weekly_html(
                data, stories, week_ahead, commentary,
                selected_sections=selected_sections,
            )
            elapsed5 = round(time.time() - t5, 1)
            total = round(time.time() - t_total, 1)
            st.write(f'✅ HTML ready — {len(html):,} chars ({elapsed5}s) · **Total: {total}s**')
        except Exception as e:
            st.error(f'❌ HTML generation failed: {e}')
            return

        if errors:
            status.update(label=f'⚠️ Done with {len(errors)} warning(s)',
                          state='complete', expanded=False)
        else:
            status.update(label='✅ Snapshot ready', state='complete', expanded=False)

    ss.html_output = html
    ss.jpeg_bytes  = None   # generate on demand
    ss.pipeline_step = 'preview'
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — PREVIEW
# ─────────────────────────────────────────────────────────────────────────────

def _step_preview():
    ss = st.session_state
    st.markdown('<div class="step-badge">STEP 3 OF 3 &nbsp;·&nbsp; PREVIEW &amp; DOWNLOAD</div>',
                unsafe_allow_html=True)

    col_back, _ = st.columns([1, 3])
    if col_back.button('← Back to review'):
        ss.pipeline_step = 'review'
        st.rerun()

    html = ss.html_output
    if not html:
        st.error('No HTML output found. Please regenerate.')
        return

    st.caption('Scroll within the preview · Download to open in browser or paste into Outlook/Gmail.')
    components.html(html, height=700, scrolling=True)

    st.markdown('---')
    week_num = ss.week_start_dt.isocalendar()[1] if ss.week_start_dt else 'XX'
    year     = ss.week_end_dt.year if ss.week_end_dt else datetime.now().year
    fname_html = f'stanc_weekly_w{week_num}_{year}.html'
    fname_jpeg = f'stanc_weekly_w{week_num}_{year}.jpg'

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label='⬇️  Download HTML',
            data=html.encode('utf-8'),
            file_name=fname_html,
            mime='text/html',
            use_container_width=True,
            type='primary',
        )

    with col2:
        if ss.jpeg_bytes:
            st.download_button(
                label='⬇️  Download JPEG',
                data=ss.jpeg_bytes,
                file_name=fname_jpeg,
                mime='image/jpeg',
                use_container_width=True,
                type='primary',
            )
        else:
            render_jpeg = st.button('🖼 Render JPEG', use_container_width=True)
            if render_jpeg:
                from html_generator import html_to_jpeg
                with st.spinner('Rendering JPEG via WeasyPrint…'):
                    jpeg_bytes, err = html_to_jpeg(html)
                if err:
                    st.error(f'JPEG render failed: {err}')
                else:
                    ss.jpeg_bytes = jpeg_bytes
                    st.rerun()

    st.markdown(
        '<div class="snap-warn">'
        '⚑ Distribute: Download → open in browser to verify → '
        'paste into Outlook (Insert HTML) or Gmail, or attach the .html file. '
        '⚠ India 10Y is Gemini-estimated — verify against CCIL/FIMMDA before sending.'
        '</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _default_week():
    today = date.today()
    days_since_fri = (today.weekday() - 4) % 7
    if days_since_fri == 0:
        days_since_fri = 7
    last_fri = today - timedelta(days=days_since_fri)
    last_mon = last_fri - timedelta(days=4)
    return last_mon, last_fri


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def render_snapshot_tab():
    _render_header()
    _init_state()

    ss = st.session_state

    # ── API key (always visible at top) ──
    api_key = _get_api_key()
    if not api_key:
        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
        with st.expander('🔑 Gemini API Key required', expanded=True):
            st.caption(
                'Get a free key at [aistudio.google.com](https://aistudio.google.com). '
                'Or add `GEMINI_API_KEY` to `.streamlit/secrets.toml`.'
            )
            key_input = st.text_input('Paste Gemini API key', type='password',
                                       placeholder='AIza…', label_visibility='collapsed')
            if key_input:
                ss['gemini_key'] = key_input
                api_key = key_input
                st.success('Key saved for this session.', icon='✅')
    else:
        st.markdown(
            '<div style="font-size:10px;color:#2e7d32;padding:4px 0;">● Gemini API key loaded</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)

    # ── Step router ──
    step = ss.get('pipeline_step', 'config')
    if step == 'config':
        _step_config(api_key)
    elif step == 'review':
        _step_review(api_key)
    elif step == 'preview':
        _step_preview()
