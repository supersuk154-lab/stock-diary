with open('tab_diary.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = lines[:10]
new_lines.append('KR_MIN_WAGE_2026 = 10_320\n')
new_lines.append('def _get_active_wage() -> int:\n')
new_lines.append('    try:\n')
new_lines.append('        if "_custom_wage" in st.session_state:\n')
new_lines.append('            return int(st.session_state["_custom_wage"])\n')
new_lines.append('    except Exception:\n')
new_lines.append('        pass\n')
new_lines.append('    try:\n')
new_lines.append('        return int(st.secrets.get("MY_HOURLY_WAGE", KR_MIN_WAGE_2026))\n')
new_lines.append('    except Exception:\n')
new_lines.append('        return KR_MIN_WAGE_2026\n\n')

idx = -1
for i, line in enumerate(lines):
    if line.startswith('def render_diary_tab'):
        idx = i
        break

if idx != -1:
    new_lines.extend(lines[26:idx])
    new_lines.extend(lines[idx:])

new_lines[5] = 'from prices import get_market_weather, _market_time_bucket, TICKER_MAP, get_realtime_price, get_realtime_prices_bulk, get_usd_to_krw\n'

with open('tab_diary.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('tab_diary.py repaired')
