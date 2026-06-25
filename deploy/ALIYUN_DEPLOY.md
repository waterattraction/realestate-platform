# 阿里云安全部署指南 — jiakubo.com

公网 IP：`47.237.121.108`  
域名：`jiakubo.com`（DNS A 记录已指向该 IP）

## 一、阿里云安全组（必须）

登录 [阿里云 ECS 控制台](https://ecs.console.aliyun.com/) → **实例** → 选中服务器 → **安全组** → **配置规则** → **入方向** → **手动添加**：

| 授权策略 | 协议 | 端口 | 授权对象 | 说明 |
|---------|------|------|---------|------|
| 允许 | TCP | **443** | `0.0.0.0/0` | HTTPS 网站访问 |
| 允许 | TCP | **80** | `0.0.0.0/0` | HTTP（证书申请 + 跳转 HTTPS） |
| 允许 | TCP | **22** | `你的办公网IP/32` | SSH（**不要用 0.0.0.0/0**，仅允许固定 IP） |

**禁止放行**（不要添加以下入方向规则）：

| 端口 | 原因 |
|------|------|
| 8000 | FastAPI 已绑定 127.0.0.1，仅 Nginx 反代 |
| 5432 | PostgreSQL 仅本机 |
| 3306、6379 等 | 未使用 |

> 若使用 **轻量应用服务器**，路径为：服务器 → **防火墙** → 添加规则（同上）。

### 可选：限制 SSH 来源

将 22 端口的授权对象设为你的公网 IP，例如 `123.45.67.89/32`。  
在终端执行 `curl ifconfig.me` 可查看当前公网 IP。

---

## 二、阿里云域名解析（已配置可跳过）

[域名控制台](https://dc.console.aliyun.com/) → `jiakubo.com` → **解析设置**：

| 记录类型 | 主机记录 | 记录值 |
|---------|---------|--------|
| A | `@` | `47.237.121.108` |
| A | `www` | `47.237.121.108`（可选，会跳转到根域名） |

---

## 三、服务器侧架构（已配置）

```
外网用户 → https://jiakubo.com:443
         → Nginx（/etc/nginx/sites-available/realestate.conf）
         → 127.0.0.1:8000（Docker backend，不对外）
         → 127.0.0.1:5432（PostgreSQL，不对外）
```

配置文件：

- `deploy/nginx/realestate-jiakubo.conf` — 正式 HTTPS 配置
- `deploy/nginx/realestate-jiakubo-http-only.conf` — 证书申请前临时 HTTP
- `deploy/nginx/proxy_params.conf` — 反代头
- `deploy/nginx/realestate-limits.conf` — 导入接口限流

---

## 四、开放安全组后，一键启用 HTTPS

在服务器执行：

```bash
chmod +x /opt/realestate-platform/deploy/scripts/enable-https-jiakubo.sh
sudo /opt/realestate-platform/deploy/scripts/enable-https-jiakubo.sh
```

脚本将自动：

1. 检测外网 80 是否可达  
2. 申请 Let's Encrypt 证书  
3. 部署 HTTPS Nginx  
4. 为 `/ingestion/` 配置 Basic Auth  
5. 启用 UFW（仅放行 22/80/443）

---

## 五、访问地址

| 用途 | URL |
|------|-----|
| 平台首页 | https://jiakubo.com/ |
| 逾期工作台 | https://jiakubo.com/overdue/workbench |
| 风控中台 | https://jiakubo.com/risk/workbench |
| 数据导入 API | https://jiakubo.com/ingestion/pipeline（需 Basic Auth） |

导入接口凭据（脚本运行后）：

```bash
sudo cat /root/.ingestion-htpasswd-credentials
```

调用示例：

```bash
curl -u ingestion:你的密码 -X POST https://jiakubo.com/ingestion/pipeline \
  -H "Content-Type: application/json" \
  -d '{"trust_product_id":1,"trust_plan_alias":"信托1号"}'
```

---

## 六、证书续期

Certbot 已配置 systemd timer，证书到期前自动续期。可手动测试：

```bash
sudo certbot renew --dry-run
```

---

## 七、生产环境建议

1. **修改数据库密码**：编辑 `docker-compose.yml` 中 `POSTGRES_PASSWORD` 与 `DATABASE_URL`，然后 `docker compose up -d`  
2. **定期备份**：`docker exec realestate-postgres pg_dump -U admin realestate > backup.sql`  
3. **新环境初始化**：参见项目根目录 `db/README.md`，执行 `./db/apply.sh baseline`  
4. **监控 443**：阿里云云监控可配置端口探测告警  
5. **后续可加**：FastAPI 登录鉴权、WAF（阿里云 Web 应用防火墙）
