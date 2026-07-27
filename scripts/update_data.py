#!/usr/bin/env python3
"""
金属价格数据更新脚本
- 白银：akshare 获取沪银期货(AG0)历史数据
- 铝：playwright 渲染长江有色金属网(hq.alu.cn)获取现货A00铝锭价格

运行环境：GitHub Actions Ubuntu
"""

import json
import re
import sys
import os

def fetch_silver_data():
    """获取白银期货数据（akshare）"""
    try:
        import akshare as ak
        df = ak.futures_zh_daily_sina(symbol='AG0')
        recent = df.tail(120)
        data = []
        for _, row in recent.iterrows():
            data.append([
                str(row['date']),
                float(row['open']),
                float(row['high']),
                float(row['low']),
                float(row['close']),
                int(row['volume'])
            ])
        print(f"✅ 白银数据: {len(data)} 条, 日期 {data[0][0]} ~ {data[-1][0]}")
        return data
    except Exception as e:
        print(f"❌ 白银数据获取失败: {e}")
        return None


def fetch_cjys_aluminum_data():
    """获取长江有色铝价数据（playwright渲染 + 表格行解析）"""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto('https://hq.alu.cn/cjys.html', timeout=30000)
            page.wait_for_timeout(5000)  # 等待JS渲染完成

            # 直接从表格行提取数据
            rows = page.query_selector_all('tr')
            data = []

            for row in rows:
                text = row.inner_text().strip()
                if '长江有色' not in text:
                    continue

                # 格式: 07-24\t长江有色\t23200\t-60\t-0.3%\t23180\t23220\t23170\t23184
                # 或: 07-15长江有色23180-90-0.4%23160232002313023078
                # 提取日期(MM-DD格式)、均价(第一个5位数)、最高、最低
                parts = re.split(r'[\t,;\s]+', text)
                if len(parts) < 2:
                    # 紧凑格式，用正则提取
                    date_match = re.match(r'(\d{2}-\d{2})', text)
                    prices = re.findall(r'(2[23]\d{3})', text)
                    if date_match and len(prices) >= 4:
                        date_str = date_match.group(1)
                        # prices[0]=均价, prices[1]=最低, prices[2]=最高
                        avg_price = int(prices[0])
                        low = int(prices[1])
                        high = int(prices[2])
                        full_date = f"2026-{date_str}"
                        data.append([full_date, avg_price, high, low, avg_price, 0])
                else:
                    # 制表符分隔格式
                    date_str = parts[0].strip()  # 如 07-24
                    if re.match(r'\d{2}-\d{2}', date_str):
                        # parts[2] = 均价, parts[5] = 最低, parts[6] = 最高
                        try:
                            avg_price = int(parts[2])
                            low = int(parts[5])
                            high = int(parts[6])
                            full_date = f"2026-{date_str}"
                            data.append([full_date, avg_price, high, low, avg_price, 0])
                        except (ValueError, IndexError):
                            pass

            browser.close()

        if not data:
            print("❌ 长江有色铝价数据未匹配到")
            return None

        # 去重
        seen = set()
        unique_data = []
        for d in data:
            if d[0] not in seen:
                seen.add(d[0])
                unique_data.append(d)

        # 按日期排序
        unique_data.sort(key=lambda x: x[0])

        # 用前一日均价填充开盘价
        for i in range(1, len(unique_data)):
            unique_data[i][1] = unique_data[i-1][4]

        print(f"✅ 长江有色铝价: {len(unique_data)} 条, 日期 {unique_data[0][0]} ~ {unique_data[-1][0]}")
        return unique_data

    except Exception as e:
        print(f"❌ 长江有色铝价获取失败: {e}")
        return None


def get_old_data(html, symbol):
    """从现有HTML中提取旧数据"""
    pattern = rf'"{symbol}":\s*(\[.*?\])'
    # 需要处理嵌套数组，用更精确的匹配
    match = re.search(rf'"{symbol}":\s*(\[\[.*?\]\])', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            pass
    return None


def update_html(ag_data, al_data):
    """更新 index.html 中的内嵌数据"""
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'index.html')

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # 构建新的数据对象
    new_data = {"AG0": ag_data, "AL0": al_data}
    new_data_str = json.dumps(new_data, ensure_ascii=False)

    # 替换 EMBEDDED_DATA - 精确匹配
    pattern = r'const EMBEDDED_DATA = \{.*?\};'
    replacement = f'const EMBEDDED_DATA = {new_data_str};'

    new_html = re.sub(pattern, replacement, html, flags=re.DOTALL, count=1)

    if new_html == html:
        print("❌ 未找到数据替换位置")
        return False

    # 更新数据来源说明中的日期
    al_latest = al_data[-1][0] if al_data else ""
    new_html = re.sub(
        r'更新至\d{4}-\d{2}-\d{2}',
        f'更新至{al_latest}',
        new_html
    )

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(new_html)

    print(f"✅ index.html 已更新")
    return True


def main():
    print("=" * 50)
    print("金属价格数据自动更新")
    print("=" * 50)

    # 获取数据
    ag_data = fetch_silver_data()
    al_data = fetch_cjys_aluminum_data()

    if not ag_data and not al_data:
        print("❌ 两个品种数据都获取失败，退出")
        sys.exit(1)

    # 保留旧数据
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'index.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    if not ag_data:
        print("⚠️ 白银数据失败，保留旧数据")
        ag_data = get_old_data(html, 'AG0')
        if ag_data:
            print(f"✅ 保留旧白银数据: {len(ag_data)} 条")

    if not al_data:
        print("⚠️ 长江铝数据失败，保留旧数据")
        al_data = get_old_data(html, 'AL0')
        if al_data:
            print(f"✅ 保留旧铝数据: {len(al_data)} 条")

    if not ag_data or not al_data:
        print("❌ 数据不完整，退出")
        sys.exit(1)

    # 更新HTML
    success = update_html(ag_data, al_data)
    if not success:
        sys.exit(1)

    print("=" * 50)
    print("✅ 数据更新完成!")
    print(f"   白银: {len(ag_data)} 条, 最新 {ag_data[-1][0]}, 收盘 {ag_data[-1][4]}")
    print(f"   长江铝: {len(al_data)} 条, 最新 {al_data[-1][0]}, 均价 {al_data[-1][4]}")


if __name__ == '__main__':
    main()
