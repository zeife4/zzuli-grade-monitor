# 郑州轻工业大学 WebVPN 系统 — 前端爬取分析

**URL**: `https://webvpn.zzuli.edu.cn`  
**爬取时间**: 2026-07-24  
**系统厂商**: 北京网瑞达科技有限公司 (WRD WebVPN)  

---

## 目录结构

```
zzuli-webvpn-frontend/
├── index.html           # 主登录页面
├── css/
│   ├── login.css        # 登录页核心样式 (含响应式)
│   ├── normalize.css    # CSS Reset
│   └── drag.css         # 滑块验证码样式
├── js/
│   ├── jquery.min.js    # jQuery 3.x
│   ├── aes-js.js        # AES 加密库 (CFB模式)
│   ├── drag.js          # 滑块验证码逻辑
│   └── wechat-font.js   # 微信字体图标
├── image/
│   ├── logo.png         # 系统 Logo
│   ├── background.jpg   # PC端背景图
│   ├── login-user.png   # 账号输入框图标
│   ├── password.png     # 密码输入框图标
│   ├── code.png         # 验证码图标
│   ├── phone.png        # 手机号图标
│   ├── question-mark.png # 帮助问号图标
│   └── loading.gif      # 加载动画
└── README.md            # 本文件
```

**注意**: 外部CDN资源 (layui, layer.js) 未被本地保存，页面引用路径为 `/wengine-vpn/...`。

---

## 页面结构

### 1. 整体布局
- 全屏背景图 (PC: `background.jpg` / 移动端: `background_mobile.jpg`)
- 顶部 Header: Logo + "WEBVPN系统" 标题
- 中间 Container (flex 布局):
  - 左: 通知面板 (notice-panel, 桌面端可见)
  - 右: 登录面板 (login-panel, 350px宽)
- 底部 Footer: "@郑州轻工业大学"

### 2. 登录方式 (Tab切换)
| Tab | type | 说明 |
|-----|------|------|
| 统一认证 | `cas` | CAS统一身份认证 (默认) |
| 账号登录 | `local` | 本地账号+密码登录 |

### 3. 表单字段
- `auth_type`: 隐藏字段, 认证类型
- `username`: 账号/手机号
- `password`: 密码 (AES-CFB加密后传输)
- `sms_code`: 短信验证码 (短信登录模式)
- `remember_cookie`: "下次自动登录" 复选框

### 4. 弹窗组件
- **双重登录认证** (`#second_login_layer`): 双因子认证时弹出，显示手机号+验证码
- **滑块验证码** (`#drag-captcha-layer`): 登录失败后的验证码
- **微信提示** (`#wechat_tip`): 微信扫码认证引导

---

## 关键前端逻辑

### 密码加密
```javascript
// 使用 AES-CFB 模式加密密码
encrypt(data[i].value, "wrdvpnisawesome!", "wrdvpnisawesome!")
// key = "wrdvpnisawesome!" (16字节)
// iv  = "wrdvpnisawesome!" (16字节)
```

### 登录流程
1. 用户在表单输入账号密码
2. 前端将密码用 AES-CFB 加密
3. `POST /do-login` 提交
4. 成功 → `location.href = res.url` 跳转
5. 失败处理:
   - `CAPTCHA_FAILED` → 弹出滑块验证码
   - `NEED_CONFIRM` → 确认踢掉已有登录
   - `NEED_TWO_STEP` → 弹出双因子认证
   - `NEED_EXTEND_FAILURE_TIME` → 延长有效期申请
   - `WEEK_PASSWORD_CHECK` → 弱密码提示
   - 其他 → 显示 `error-message`

### 滑块验证码流程
1. 调用 `GET /login/image?_=timestamp` 获取验证码图片
2. 用户拖动滑块
3. 提交 `POST /login/verify` (参数: `w`距离, `t`时间, `locations`轨迹)
4. 成功 → 自动触发登录

### CAS 统一认证
- 点击"CAS统一身份认证登录"按钮
- 跳转到 `/login?cas_login=true`
- 与学校统一身份认证系统对接

---

## 响应式设计

| 断点 | 行为 |
|------|------|
| `>769px` | 桌面端: 通知面板+登录面板并排, PC背景图 |
| `≤769px` | 平板: 通知面板隐藏, 移动端背景图, 登录面板居中500px |
| `≤416px` | 手机: 登录面板宽度90% |

---

## 外部依赖

| 库 | 路径 | 用途 |
|---|------|------|
| jQuery | `/wengine-vpn/js/js/jquery.min.js` | DOM操作 |
| layer.js | `/wengine-vpn/js/layer-v3.1.1/layer.js` | 弹窗组件 |
| layui | `/wengine-vpn/js/layui/layui.js` | UI框架(表单等) |
| aes-js | `/wengine-vpn/js/aes-js.js` | AES密码加密 |
| Quill | `quill.snow.css` | 富文本编辑器样式(通知区域) |
| TouchSwipe | (内联于页面) | 移动端触摸适配 |

---

## 安全分析摘要

1. **密码加密**: 使用 AES-CFB 加密，但密钥硬编码在前端 (`"wrdvpnisawesome!"`)
2. **验证码**: 滑块验证码作为防爆破手段
3. **双因子认证**: 支持短信二次验证
4. **会话管理**: 支持"踢掉已登录设备"和"下次自动登录"
5. **CSRF**: 未发现显式的 CSRF Token 机制
6. **CSP**: 未发现 Content-Security-Policy 头部

---

## 通知内容

```
为了方便在校园网外访问内网和图书馆资源，经过信息化管理中心前期部署和测试，
开通了WebVPN服务，无需安装客户端和插件，支持电脑和手机直接使用，
为了获得更好的体验建议使用Chrome、Firefox、IE11、Edge、Safari等浏览器。

请选择统一认证，使用CAS统一身份认证登录。

WebVPN使用方法详见 WebVPN使用指南 (https://ic.zzuli.edu.cn/2022/0104/c14804a335191/page.htm)
```

---

> **免责声明**: 此分析仅用于学习研究目的。该系统的版权归郑州轻工业大学信息化管理中心及北京网瑞达科技有限公司所有。

---

## 成绩监控脚本 — 使用指南

### 功能

自动监控教务系统成绩变化，有新成绩时桌面通知 + 微信推送。

```
扫码登录 → 每5分钟自动检查 → 成绩有变化 → 🔔 通知
```

### 环境要求

- Python 3.9+
- Windows / macOS / Linux

### 安装

#### 方式一：下载压缩包（推荐，无需 Git）

1. 打开 [Releases](https://github.com/zeife4/zzuli-grade-monitor/releases) 页面
2. 下载最新版 `zzuli-grade-monitor-vX.X.zip`
3. 解压到任意目录，打开终端进入该目录
4. 执行以下命令：

```bash
# 安装依赖
pip install playwright beautifulsoup4

# 安装浏览器 (Chromium)
playwright install chromium

# 创建配置文件
copy config.example.json config.json    # Windows
# cp config.example.json config.json    # macOS / Linux
```

#### 方式二：Git 克隆

```bash
# 1. 克隆项目
git clone git@github.com:zeife4/zzuli-grade-monitor.git
cd zzuli-grade-monitor

# 2. 安装依赖
pip install playwright beautifulsoup4

# 3. 安装浏览器 (Chromium)
playwright install chromium

# 4. 创建配置文件
cp config.example.json config.json
```

### 配置

编辑 `config.json`：

```json
{
    "webvpn_base": "https://webvpn.zzuli.edu.cn",
    "check_interval_seconds": 300,       // 检查间隔(秒), 默认5分钟
    "max_retry_on_failure": 3,           // 失败重试次数
    "notify": {
        "desktop": true,                 // 桌面通知
        "sound": true,                   // 声音提醒
        "wechat": {
            "enabled": false,            // 微信推送 (需注册 Server酱)
            "sendkey": "SCTxxxxxxxx"     // https://sct.ftqq.com/ 获取
        }
    }
}
```

#### 微信通知 (可选)

1. 打开 [Server酱](https://sct.ftqq.com/) 扫码登录
2. 获取 SendKey
3. 填入 `config.json` 的 `notify.wechat.sendkey`
4. 将 `enabled` 改为 `true`

### 运行

```bash
python grade_monitor.py
```

首次运行会打开浏览器，用手机**微信/钉钉扫码**登录即可，之后脚本会自动监控。

### 运行时命令

| 输入 | 功能 |
|------|------|
| `aaa` | 立即检查一次成绩 |
| `Enter` | 会话过期后重新扫码 |

### 输出文件

| 文件 | 说明 |
|------|------|
| `grade_snapshot.json` | 当前成绩快照 |
| `grade_history.log` | 成绩变化历史 |
| `change_*.txt` | 每次变化的详细记录 |
| `monitor.log` | 运行日志 |

### 工作原理

```
扫码登录 (Playwright 浏览器)
       │
       ▼
  导航到成绩页 (VPN门户 → 教务系统 → 学业成绩 → 检索)
       │
       ▼
  解析成绩表格 (BeautifulSoup)
       │
       ▼
  对比上次快照 ──有变化──▶ 桌面通知 + 微信推送 + 记录历史
       │                        │
       │ 无变化                  │
       ▼                        ▼
  等待5分钟 ◀────────────── 更新快照
```

> **免责声明**: 本脚本仅用于学习研究目的。使用者自行承担使用风险。
