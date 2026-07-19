# 监控模版扩展列回填

## 问题

`trust_asset_monitor_records` 模版扩展列（城市、小区、合同等）在历史导入时未写入，库内全空；原始 Excel 与 `/data/uploads` 中文件仍完整。

## 方案

按 `(trust_product_id, source_file_name, source_sheet_name)` 找回上传文件，解析扩展列，`UPDATE` **仅补 NULL**，不改金额/逾期/风险。

## 执行

```bash
# 容器内
docker compose exec -T backend python /data/repo/scripts/ops/backfill_monitor_template_columns.py --dry-run
docker compose exec -T backend python /data/repo/scripts/ops/backfill_monitor_template_columns.py --apply
```

产物：`/data/uploads/ops/backfill_monitor_template_columns/`

## 风险

P2：多产品、可回滚（仅填空；如需回滚可从备份表清空扩展列，默认不建全表备份因体积大，apply 前 dry-run 对照 CSV）。

## 程序侧防复发

导入路径已支持扩展列；列表城市不再 COALESCE 发行城市。
