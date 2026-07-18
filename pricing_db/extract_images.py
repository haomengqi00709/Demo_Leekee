"""
从 xlsx 内抽取内嵌图片，并给出每张图锚定的 (sheet, row, col)。
用 zipfile + drawing XML 解析，避免大文件用 openpyxl 全量加载。
返回: list[dict(sheet_name, from_row(0based), from_col(0based), media_name, ext, data(bytes))]
"""
import zipfile, os, re
from xml.etree import ElementTree as ET

NS = {
    'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
    'a':   'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r':   'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'pr':  'http://schemas.openxmlformats.org/package/2006/relationships',
    'wb':  'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
}

def _rels(z, part):
    """读取某个 part 的 .rels，返回 {rId: target(相对 part 目录)}"""
    d = os.path.dirname(part)
    relpath = f"{d}/_rels/{os.path.basename(part)}.rels"
    out = {}
    if relpath not in z.namelist():
        return out
    root = ET.fromstring(z.read(relpath))
    for rel in root:
        rid = rel.get('Id'); tgt = rel.get('Target')
        # 归一化相对路径
        full = os.path.normpath(os.path.join(d, tgt)).replace('\\', '/')
        out[rid] = full
    return out

def sheet_name_to_part(z):
    """返回 {sheet_name: worksheets/sheetN.xml}"""
    wbxml = ET.fromstring(z.read('xl/workbook.xml'))
    wbrels = _rels(z, 'xl/workbook.xml')
    out = {}
    for s in wbxml.find('wb:sheets', NS):
        name = s.get('name')
        rid = s.get('{%s}id' % NS['r'])
        if rid in wbrels:
            out[name] = wbrels[rid]
    return out

def extract(path):
    results = []
    try:
        z = zipfile.ZipFile(path)
    except Exception:
        return results
    names = set(z.namelist())
    if not any(n.startswith('xl/media/') for n in names):
        z.close(); return results
    try:
        name2part = sheet_name_to_part(z)
    except Exception:
        name2part = {}
    for sheet_name, part in name2part.items():
        srels = _rels(z, part)          # sheet 的 rels
        # 找 drawing 关系
        drawings = [t for t in srels.values() if '/drawings/' in t and t.endswith('.xml')]
        for draw in drawings:
            if draw not in names:
                continue
            drels = _rels(z, draw)      # drawing 的 rels: rId -> media
            try:
                droot = ET.fromstring(z.read(draw))
            except Exception:
                continue
            for anchor in droot:
                tag = anchor.tag.split('}')[-1]
                if tag not in ('twoCellAnchor', 'oneCellAnchor', 'absoluteAnchor'):
                    continue
                frm = anchor.find('xdr:from', NS)
                row = col = None
                if frm is not None:
                    rc = frm.find('xdr:row', NS); cc = frm.find('xdr:col', NS)
                    row = int(rc.text) if rc is not None else None
                    col = int(cc.text) if cc is not None else None
                # 找 blip embed
                blip = anchor.find('.//a:blip', NS)
                if blip is None:
                    continue
                embed = blip.get('{%s}embed' % NS['r'])
                media = drels.get(embed)
                if not media or media not in names:
                    continue
                ext = os.path.splitext(media)[1].lstrip('.').lower()
                try:
                    data = z.read(media)
                except Exception:
                    continue
                results.append(dict(sheet_name=sheet_name, from_row=row, from_col=col,
                                    media_name=os.path.basename(media), ext=ext, data=data))
    z.close()
    return results

if __name__ == '__main__':
    import sys
    for r in extract(sys.argv[1]):
        print(r['sheet_name'], r['from_row'], r['from_col'], r['media_name'], len(r['data']))
