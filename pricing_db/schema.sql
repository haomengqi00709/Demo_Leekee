-- =====================================================================
--  李记包装 报价系统 · 结构化数据库 schema (SQLite)
--  生成脚本: build_db.py   |  见 PROJECT.md
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ---------- 来源文件登记 ----------
DROP TABLE IF EXISTS source_files;
CREATE TABLE source_files (
    id           INTEGER PRIMARY KEY,
    rel_path     TEXT UNIQUE,          -- 相对本项目根目录的路径
    category     TEXT,                 -- invoice | master | series | single | glass | supplier_quote | other
    file_date    TEXT,                 -- 从文件名解析出的日期(如有)
    sheet_count  INTEGER,
    image_count  INTEGER
);

-- ---------- 核心：价目明细（长表，一行 = 一个 工艺档位→价格）----------
DROP TABLE IF EXISTS price_items;
CREATE TABLE price_items (
    id             INTEGER PRIMARY KEY,
    source_file_id INTEGER REFERENCES source_files(id),
    sheet_name     TEXT,
    row_index      INTEGER,            -- 在原表中的行号(1-based)
    series_code    TEXT,               -- 所属套系 H###（如有）
    product_code   TEXT,              -- 该行主编号(原样，可能含多码 "A/B")
    capacity       TEXT,               -- 容量(原样，可能含多值)
    component      TEXT,               -- 配件结构 / 部件名称
    process_desc   TEXT,               -- 工艺说明（价格随此变化的关键维度）
    unified_price  REAL,               -- 统一价格 / 统一报价（对外基准价）
    list_price     REAL,               -- 门市价格 / 内部成本价（如有）
    supplier       TEXT,               -- 供应商
    supplier_model TEXT,               -- 供应商型号(如有)
    price_year     INTEGER,            -- 价格年份(从列名/文件名推断)
    remark         TEXT,               -- 备注
    orientation    TEXT,               -- long | wide (原表方向)
    raw_json       TEXT                -- 原始整行(JSON)，避免信息丢失，便于回溯
);
CREATE INDEX idx_pi_product ON price_items(product_code);
CREATE INDEX idx_pi_series  ON price_items(series_code);

-- ---------- 单个编号 → 价目明细 的展开映射（拆分 "CC20596/CC20659" 这类多码）----------
DROP TABLE IF EXISTS price_item_code;
CREATE TABLE price_item_code (
    price_item_id INTEGER REFERENCES price_items(id),
    code          TEXT
);
CREATE INDEX idx_pic_code ON price_item_code(code);

-- ---------- 产品编码主表（从各表聚合出的去重编码）----------
DROP TABLE IF EXISTS products;
CREATE TABLE products (
    code          TEXT PRIMARY KEY,
    prefix        TEXT,                -- H / CB / CC / CA / SH / LB ...
    product_type  TEXT,               -- series | bottle | pump | dropper | cover | cap | component | supplier_model
    name          TEXT,                -- 物料名称(如有)
    capacity      TEXT,
    weight_g      REAL,
    default_supplier TEXT,
    n_price_rows  INTEGER              -- 关联到的价目行数
);

-- ---------- 玻璃瓶单品统一报价（光瓶价 + 蒙砂费 → 统一价）----------
DROP TABLE IF EXISTS glass_bottles;
CREATE TABLE glass_bottles (
    id             INTEGER PRIMARY KEY,
    source_file_id INTEGER REFERENCES source_files(id),
    sheet_name     TEXT,               -- 乳液瓶 / 膏霜瓶 / 外购瓶 / 各年份新开发 ...
    dev_year       TEXT,               -- 开发年份
    material_code  TEXT,               -- 物料编码
    material_name  TEXT,
    capacity       TEXT,
    weight_g       REAL,
    unified_price  REAL,               -- 统一价格
    bare_price     REAL,               -- 光瓶价格
    frosting_fee   REAL,               -- 蒙砂费用
    raw_json       TEXT
);
CREATE INDEX idx_gb_code ON glass_bottles(material_code);

-- ---------- 库存 ----------
DROP TABLE IF EXISTS inventory;
CREATE TABLE inventory (
    id             INTEGER PRIMARY KEY,
    source_file_id INTEGER REFERENCES source_files(id),
    material_code  TEXT,               -- 带批次后缀的完整编码
    base_code      TEXT,               -- 去后缀的基础编码
    stock_qty      REAL,
    description    TEXT,
    bottle_weight  REAL,
    stock_days     REAL,
    note           TEXT
);

-- ---------- 图片：抽取后与产品编码对应 ----------
DROP TABLE IF EXISTS images;
CREATE TABLE images (
    id             INTEGER PRIMARY KEY,
    source_file_id INTEGER REFERENCES source_files(id),
    sheet_name     TEXT,
    anchor_row     INTEGER,            -- 图片锚定的行(1-based)
    anchor_col     INTEGER,            -- 图片锚定的列(1-based)
    product_code   TEXT,               -- 依据锚定行推断出的产品编码
    series_code    TEXT,
    media_name     TEXT,               -- 原 xl/media/ 内名字
    ext            TEXT,
    saved_path     TEXT,               -- 抽取后保存的相对路径
    mapped         INTEGER             -- 1=已映射到编码, 0=未映射
);
CREATE INDEX idx_img_code ON images(product_code);

-- ---------- 供应商（去重）----------
DROP TABLE IF EXISTS suppliers;
CREATE TABLE suppliers (
    name          TEXT PRIMARY KEY,
    n_items       INTEGER
);

-- ---------- 对外报价单 / 发票 ----------
DROP TABLE IF EXISTS invoices;
CREATE TABLE invoices (
    id            INTEGER PRIMARY KEY,
    source_file_id INTEGER REFERENCES source_files(id),
    doc_type      TEXT,                -- proforma_invoice | quotation
    buyer         TEXT,
    incoterm      TEXT,                -- FOB Shanghai / FOB Guangzhou
    currency      TEXT,                -- EUR / USD
    payment_term  TEXT,
    total_amount  REAL,
    validity      TEXT
);
DROP TABLE IF EXISTS invoice_lines;
CREATE TABLE invoice_lines (
    id            INTEGER PRIMARY KEY,
    invoice_id    INTEGER REFERENCES invoices(id),
    line_no       TEXT,
    description   TEXT,
    product_codes TEXT,
    quantity      REAL,
    unit_price    REAL,
    amount        REAL,
    raw_json      TEXT
);

-- =====================================================================
--  以下为“规则/参数”表：先按通话中确认的默认值播种，
--  标记 confirmed=0 表示待与客户核对（阶段2细化）。
-- =====================================================================

-- 客户加成率
DROP TABLE IF EXISTS customer_markups;
CREATE TABLE customer_markups (
    tier          TEXT,                -- 示例分档
    markup_pct    REAL,                -- 20 / 30 / 50
    note          TEXT,
    confirmed     INTEGER DEFAULT 0
);

-- 数量阶梯折扣
DROP TABLE IF EXISTS qty_discount_tiers;
CREATE TABLE qty_discount_tiers (
    min_qty       INTEGER,             -- 起订量下限
    note          TEXT,
    confirmed     INTEGER DEFAULT 0
);

-- 表面/印刷等附加工艺费（每次/每个）
DROP TABLE IF EXISTS surface_fees;
CREATE TABLE surface_fees (
    process       TEXT,                -- 普通印刷 / 烫金 / 蒙砂 ...
    fee           REAL,
    unit          TEXT,                -- 每次 / 每个
    note          TEXT,
    confirmed     INTEGER DEFAULT 0
);

-- =====================================================================
--  便捷视图 (VIEWS)
-- =====================================================================

-- 每个 (编码, 工艺) 的“最新有效价”：优先价格年份大、其次来源文件新
DROP VIEW IF EXISTS v_price_latest;
CREATE VIEW v_price_latest AS
SELECT code, series_code, capacity, component, process_desc, unified_price, list_price,
       supplier, price_year, source_file_id
FROM (
  SELECT pic.code, pi.*,
         ROW_NUMBER() OVER (
           PARTITION BY pic.code, pi.process_desc
           ORDER BY COALESCE(pi.price_year,0) DESC, pi.source_file_id DESC
         ) rn
  FROM price_item_code pic JOIN price_items pi ON pi.id=pic.price_item_id
  WHERE pi.unified_price IS NOT NULL
) WHERE rn=1;

-- 套系 → 其包含的部件清单
DROP VIEW IF EXISTS v_series_components;
CREATE VIEW v_series_components AS
SELECT series_code, product_code, capacity,
       GROUP_CONCAT(DISTINCT component) components,
       COUNT(*) n_process_options,
       MIN(unified_price) price_min, MAX(unified_price) price_max
FROM price_items
WHERE series_code IS NOT NULL AND product_code IS NOT NULL
GROUP BY series_code, product_code, capacity;

-- 编码 → 图片
DROP VIEW IF EXISTS v_product_image;
CREATE VIEW v_product_image AS
SELECT product_code, MIN(saved_path) image_path, COUNT(*) n_images
FROM images WHERE mapped=1 AND product_code IS NOT NULL
GROUP BY product_code;
