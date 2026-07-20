# 部署指南 — GitHub Pages (前端) + Railway (后端)

> **给执行部署的 AI agent**:本文档是完整的部署手册。按顺序执行即可将项目上线。
> 最终用户访问 `https://<github-user>.github.io/<repo>/` 看到前端界面,后端 API 跑在 Railway。

---

## 1. 项目架构概览

```
用户浏览器
  │
  ├── GitHub Pages (静态前端)
  │     纯 HTML + xeokit 2.6 + Alpine.js 3.14
  │     无构建步骤,直接 serve
  │     URL: https://<user>.github.io/<repo>/
  │
  └── Railway (Python 后端)
        FastAPI + ifcopenshell + Pydantic v2
        URL: https://<app>.up.railway.app
        端口: Railway 自动分配 PORT 环境变量
```

**关键设计**:
- 前端是纯静态文件(`index.html` + `src/*.js` + `lib/*.js/.wasm`),不需要 Node.js 构建
- 后端是 FastAPI 单进程,内存态 session(无数据库依赖)
- 前端通过 `fetch()` 调用后端 API,CORS 已在后端配置为 `allow_origins=["*"]`
- 前端 `api.js` 第 1 行 `const API_BASE = ''` 需要改为 Railway 后端 URL

---

## 2. 前置条件

| 项 | 要求 |
|---|---|
| GitHub 账号 | 有仓库创建权限 |
| Railway 账号 | 可用 GitHub OAuth 登录,有免费额度($5/月) |
| Git | 本地已安装 |
| 文件大小 | `frontend/lib/` 下 xeokit+web-ifc 约 8MB,Railway 免费额度足够 |

---

## 3. 后端部署 — Railway

### 3.1 准备启动配置

后端入口是 `backend/app/main.py`,FastAPI app 对象名 `app`。
Railway 需要 `Procfile` 或自动检测。**推荐用 `Procfile` 显式指定**。

在 `fsb-door-check/backend/` 下创建 `Procfile`:

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

> Railway 会注入 `PORT` 环境变量(通常 8000 或随机端口)。
> `--host 0.0.0.0` 必须有,Railway 的健康检查从容器外部访问。

### 3.2 ifcopenshell Linux 依赖

ifcopenshell 在 Linux 上需要系统级编译依赖。Railway 使用 Nixpacks 构建器,
**通常能自动安装** ifcopenshell 的 pip 包(它有预编译 wheel)。

如果构建失败,在 Railway 项目根目录创建 `nixpacks.toml`:

```toml
[phases.setup]
nixPkgs = ["python313", "gcc", "cmake", "libxml2", "libxml2-dev"]
```

> 大多数情况下不需要这个文件 — ifcopenshell 0.8+ 有 manylinux wheel。
> 先尝试不带 nixpacks.toml 部署,失败再加。

### 3.3 Railway 部署步骤

1. **推代码到 GitHub**(如果还没有):
   ```bash
   git push origin main
   ```

2. **在 Railway 创建项目**:
   - 访问 https://railway.app → New Project → Deploy from GitHub repo
   - 选择包含 `fsb-door-check/` 的仓库
   - **Root Directory 设为 `fsb-door-check/backend`**(关键!否则找不到 `app.main`)
     - Settings → Build → Root Directory: `fsb-door-check/backend`

3. **Railway 自动构建**:
   - 检测到 `requirements.txt` → pip install
   - 检测到 `Procfile` → 用其中的命令启动
   - 构建日志里应看到 `Successfully installed ifcopenshell-0.8.x`

4. **获取 Railway URL**:
   - Settings → Networking → Generate Domain
   - 得到类似 `https://fsb-door-check-production.up.railway.app`
   - 测试: `curl https://<your-url>/health` → `{"status":"ok",...}`

5. **验证 Swagger**: 访问 `https://<your-url>/docs` — 应看到 FastAPI Swagger UI

### 3.4 常见问题

| 问题 | 解决 |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Root Directory 没设对,必须是 `fsb-door-check/backend` |
| `ifcopenshell install failed` | 加 `nixpacks.toml`(见 3.2),或改 `requirements.txt` 为 `ifcopenshell==0.8.5` 锁版本 |
| `Port binding failed` | 确认 Procfile 用 `$PORT` 而非硬编码 8000 |
| `/health` 返回 404 | Railway 可能把 root path 吃掉,检查是否有多余的 path prefix |
| 前端加载后 3D 不显示 | 这是前端问题,见 §4;后端只管 API |

---

## 4. 前端部署 — GitHub Pages

### 4.1 修改 API 基址

前端 `frontend/src/api.js` 第 1 行:

```javascript
// 改前(本地开发,同源)
const API_BASE = '';

// 改后(指向 Railway 后端)
const API_BASE = 'https://<your-railway-url>';
```

> **不要**在 URL 末尾加 `/`。`api.js` 里的 fetch 拼接是 `${API_BASE}/model/upload`。

### 4.2 处理 GitHub Pages 子路径

GitHub Pages URL 是 `https://<user>.github.io/<repo>/`,前端资源加载路径
需要考虑这个 `/<repo>/` 前缀。

检查 `frontend/index.html` 里的资源引用:
- `<script type="module" src="/src/app.js">` → 需改为相对路径 `src/app.js`
- `<script defer src="/lib/alpine.cdn.min.js">` → 需改为 `lib/alpine.cdn.min.js`

**修改 `index.html`**:
```html
<!-- 改前 -->
<script type="module" src="/src/app.js"></script>
<script defer src="/lib/alpine.cdn.min.js"></script>

<!-- 改后(去掉前导斜杠,用相对路径) -->
<script type="module" src="./src/app.js"></script>
<script defer src="./lib/alpine.cdn.min.js"></script>
```

> 如果仓库就放在 GitHub 账号根 `<user>.github.io/repo` 仓库(即 repo 名 = 用户名),
> 则不需要改,资源路径 `/src/app.js` 就能直接工作。

### 4.3 检查 `viewer.js` 的 wasm 路径

`frontend/src/viewer.js` 里 web-ifc wasm 加载路径:
搜索 `web-ifc.wasm`,确认路径是相对路径(`lib/web-ifc.wasm` 或 `./lib/web-ifc.wasm`),
不是绝对路径(`/lib/web-ifc.wasm`)。

### 4.4 GitHub Pages 部署步骤

**方式 A: 直接从 main 分支 serve(最简单)**

1. 确保 `frontend/` 目录在仓库根(或子目录)
2. GitHub 仓库 → Settings → Pages
3. Source: Deploy from a branch
4. Branch: `main` / `/(root)` 或 `main` / `/fsb-door-check`
5. 保存,等 1-2 分钟,Pages 会显示 URL

**问题**: GitHub Pages 只能 serve 仓库根或 `docs/` 目录。
如果前端在 `fsb-door-check/frontend/`,GitHub Pages 默认 serve 不到。

**方式 B: 用 GitHub Action 部署(推荐)**

在仓库根创建 `.github/workflows/deploy-frontend.yml`:

```yaml
name: Deploy Frontend to GitHub Pages

on:
  push:
    branches: [main]
    paths:
      - 'fsb-door-check/frontend/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - name: Setup Pages
        uses: actions/configure-pages@v4
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: ./fsb-door-check/frontend
      - name: Deploy to GitHub Pages
        id: deploy
        uses: actions/deploy-pages@v4
```

然后:
1. GitHub 仓库 → Settings → Pages → Source: **GitHub Actions**
2. push 代码到 main 分支
3. Action 自动运行,部署后 Pages 显示 `https://<user>.github.io/<repo>/`

### 4.5 验证前端

1. 访问 `https://<user>.github.io/<repo>/`
2. 应看到 FSB Door Check 界面(顶部蓝条 + 左侧 3D 区域 + 右侧栏)
3. 点 "Load IFC" → 选一个 `.ifc` 文件 → 3D 模型应渲染
4. 如果 3D 不显示但侧栏有数据 → 前端 wasm 路径问题(见 4.3)
5. 如果侧栏也没数据 → F12 看 Network,检查 API 请求是否到了 Railway

---

## 5. 环境变量总结

| 在哪里 | 变量 | 值 | 说明 |
|---|---|---|---|
| Railway | `PORT` | (Railway 自动注入) | 后端监听端口 |
| 前端 `api.js` | `API_BASE` | `https://<railway-url>` | 后端 API 基址(硬编码在代码里) |
| GitHub Action | 无 | — | 前端是纯静态,无环境变量 |

> **没有数据库、没有 API key、没有 OAuth** — 这个项目不需要任何密钥管理。

---

## 6. 部署后验证清单

- [ ] `https://<railway-url>/health` 返回 `{"status":"ok"}`
- [ ] `https://<railway-url>/docs` 显示 Swagger UI
- [ ] `https://<user>.github.io/<repo>/` 显示前端界面
- [ ] 前端 "Load IFC" 能成功上传文件(Network 标签看到 POST `/model/upload` → 200)
- [ ] 3D 模型在浏览器里渲染出来
- [ ] "Run Check" 按钮能跑出 pass/fail 统计
- [ ] 点门能显示 Door tab 详情
- [ ] JSON 导出能下载文件

---

## 7. 备选方案 — 全部部署在 Railway(更简单)

如果 GitHub Pages 的子路径问题太麻烦,可以**把前端也交给 Railway serve**:
后端 `main.py` 最后一行已经 mount 了 `frontend/` 为静态文件:

```python
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
```

这样只需要一个 Railway 服务,访问 `https://<railway-url>/` 既是前端又是 API。
**`api.js` 的 `API_BASE` 保持空字符串即可**(同源)。

优点: 无 CORS、无子路径、配置最简单
缺点: URL 是 `xxx.up.railway.app` 而非 GitHub 域名; Railway 免费额度有限

> 如果用户坚持要 GitHub 域名,用 §3+§4 的分离部署。
> 如果用户只想要能跑,用这个方案。

---

## 8. 项目文件结构(部署相关)

```
仓库根/
├── fsb-door-check/
│   ├── backend/
│   │   ├── Procfile              ← 需创建(§3.1)
│   │   ├── nixpacks.toml         ← 可选,构建失败时创建(§3.2)
│   │   ├── requirements.txt      ← 已有,Railway 据此 pip install
│   │   ├── app/
│   │   │   ├── main.py           ← FastAPI 入口,CORS=*,mount frontend/
│   │   │   └── ...
│   │   ├── presets/              ← 法规数据 JSON(运行时读取)
│   │   └── tests/                ← 部署时不需要跑
│   ├── frontend/
│   │   ├── index.html            ← 需改资源路径为相对路径(§4.2)
│   │   ├── src/
│   │   │   ├── api.js            ← 需改 API_BASE(§4.1)
│   │   │   ├── app.js
│   │   │   └── viewer.js
│   │   └── lib/                  ← xeokit + web-ifc wasm(约 8MB)
│   └── docs/
└── .github/workflows/
    └── deploy-frontend.yml       ← 需创建(§4.4 方式 B)
```

---

## 9. 费用估算

| 服务 | 免费额度 | 本项目用量 |
|---|---|---|
| GitHub Pages | 公开仓库免费 | 静态文件 ~8MB,远低于限制 |
| Railway | $5/月免费额度 | 每次构建 ~2 分钟,运行时 ~50MB 内存,月消耗约 $1-3 |

> 如果只是演示用,跑完就 sleep,Railway 基本不花钱。
> Railway 免费额度用完后服务会暂停(不是删除),充值后恢复。

---

## 10. 给部署 agent 的精简执行清单

```
1. cd fsb-door-check/backend && 创建 Procfile (内容见 §3.1)
2. git push 到 GitHub
3. Railway: New Project → 选 repo → Root Directory = fsb-door-check/backend → Deploy
4. 等 Railway 构建完成,记下 URL (如 https://xxx.up.railway.app)
5. curl https://xxx.up.railway.app/health 验证后端
6. 改 frontend/src/api.js 第1行: const API_BASE = 'https://xxx.up.railway.app'
7. 改 frontend/index.html: 资源路径去掉前导斜杠 (§4.2)
8. 创建 .github/workflows/deploy-frontend.yml (§4.4)
9. git commit + push
10. GitHub Settings → Pages → Source: GitHub Actions
11. 等 Action 跑完,访问 GitHub Pages URL 验证
12. 如果全在 Railway 更简单: 跳过 6-11,直接访问 Railway URL
```
