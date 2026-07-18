# -*- coding: utf-8 -*-
"""上传新报价单 Excel → 复用 build_db 的解析器读成价目行 → 预览 → 合并进 price_items。"""
import os, sys, json

PDB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pricing_db")
if PDB not in sys.path:
    sys.path.insert(0, PDB)
import build_db as B  # 复用: load_rows_xlsx/xls, parse_table, series_from, find_year, split_codes, file_date

def parse_upload(tmp_path, filename):
    """→ list[item]，item 结构与 build_db.parse_table 输出一致，另加 _sheet。"""
    if filename.lower().endswith(".xls"):
        rows_by_sheet = B.load_rows_xls(tmp_path)
    else:
        rows_by_sheet = B.load_rows_xlsx(tmp_path)
    fdef = B.series_from(filename)
    fyear = B.find_year(filename)
    items = []
    for sheet, rows in rows_by_sheet.items():
        sser = B.series_from(sheet) or fdef
        its, _ = B.parse_table(rows, file_default_series=sser, price_year_default=fyear)
        for it in its:
            it["_sheet"] = sheet
            items.append(it)
    return items

def summarize(con, items):
    series = sorted({it["series"] for it in items if it["series"]})
    codes = set()
    for it in items:
        for c in B.split_codes(it["code"]):
            codes.add(c)
    ex_series = {r[0] for r in con.execute(
        "SELECT DISTINCT series_code FROM price_items WHERE series_code IS NOT NULL")}
    ex_codes = {r[0] for r in con.execute("SELECT DISTINCT code FROM price_item_code")}
    new_series = [s for s in series if s not in ex_series]
    new_codes = sorted(codes - ex_codes)
    dup_codes = sorted(codes & ex_codes)
    sample = [{
        "series": it["series"], "code": it["code"], "cap": it["cap"],
        "component": it["comp"], "process": it["process"],
        "price": it["unified"], "supplier": it["sup"],
    } for it in items[:15]]
    return {
        "n_rows": len(items),
        "series": series, "new_series": new_series,
        "n_new_codes": len(new_codes), "new_codes": new_codes[:30],
        "n_dup_codes": len(dup_codes), "dup_codes": dup_codes[:30],
        "sample": sample,
    }

def do_import(con, items, filename):
    cur = con.cursor()
    cur.execute("""INSERT INTO source_files(rel_path,category,file_date,sheet_count,image_count)
                   VALUES(?,?,?,?,?)""",
                (f"upload/{filename}", "upload", B.file_date(filename), 1, 0))
    fid = cur.lastrowid
    n = 0
    for it in items:
        cur.execute("""INSERT INTO price_items
            (source_file_id,sheet_name,row_index,series_code,product_code,capacity,component,
             process_desc,unified_price,list_price,supplier,supplier_model,price_year,remark,orientation,raw_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (fid, it.get("_sheet"), it.get("row"), it["series"], it["code"], it["cap"], it["comp"],
             it["process"], it["unified"], it["list"], it["sup"], it["smodel"], it["year"],
             it["remark"], it["orient"], it["raw"]))
        pid = cur.lastrowid
        for c in B.split_codes(it["code"]):
            cur.execute("INSERT INTO price_item_code(price_item_id,code) VALUES(?,?)", (pid, c))
        n += 1
    return fid, n
