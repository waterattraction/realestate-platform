# 还款明细披露扩展列回填

## 问题

`trust_repayment_detail_records` 披露扩展列（资产包编号、当前还款方、计划/装修/累计/余额等）历史导入未写入。

## 方案

按 `(trust_product_id, source_file_name, source_sheet_name)` 找回上传文件，解析后按  
`custody + source + repayment_date + amount + period_no` 对齐，`UPDATE` 仅补 NULL。

## 执行

```bash
docker compose exec -T backend python /data/repo/scripts/ops/backfill_repayment_template_columns.py --dry-run
docker compose exec -T backend python /data/repo/scripts/ops/backfill_repayment_template_columns.py --apply
```

产物：`/data/uploads/ops/backfill_repayment_template_columns/`
