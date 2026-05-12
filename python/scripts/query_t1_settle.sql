-- 查询 t-1 天各品种最新合约的结算价
--
-- 说明：
--   1. "t-1" 指数据库中最近有数据日期的前一个交易日（自动识别，无需手动指定日期）
--   2. "各品种最新"指同一品种下合约月份最大的那条记录（如 AU2506, AU2508, AU2512 中取 AU2512）
--   3. ts_code 格式：{品种代码}{合约月份}.{交易所}，例如 AU2506.SHF
--
-- 用法：在 psql 或任何 PostgreSQL 客户端中直接执行

WITH
-- t 日：数据库中最新有数据的交易日
t_date AS (
    SELECT MAX(trade_date) AS trade_date
    FROM fut_settle
),
-- t-1 日：t 日之前的最近一个交易日
t1_date AS (
    SELECT MAX(trade_date) AS trade_date
    FROM fut_settle
    WHERE trade_date < (SELECT trade_date FROM t_date)
),
-- 提取品种代码和合约月份
extracted AS (
    SELECT
        fs.ts_code,
        fs.trade_date,
        fs.settle,
        fs.exchange,
        -- 提取品种代码：去掉数字及之后的部分
        regexp_replace(fs.ts_code, '[0-9].*$', '') AS variety_code,
        -- 提取合约月份并转为整数，用于排序
        (regexp_match(fs.ts_code, '[0-9]+'))[1]::int AS contract_month
    FROM fut_settle fs
    WHERE fs.trade_date = (SELECT trade_date FROM t1_date)
)
SELECT DISTINCT ON (variety_code)
    variety_code                     AS 品种代码,
    ts_code                          AS 合约代码,
    trade_date::date                 AS 交易日,
    settle                           AS 结算价,
    exchange                         AS 交易所
FROM extracted
ORDER BY variety_code, contract_month DESC;
