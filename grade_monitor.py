#!/usr/bin/env python3
"""
郑州轻工业大学 WebVPN 成绩监控脚本
========================================
Playwright 全程驱动, 纯点击模拟导航.
扫码登录 → 浏览器后台驻留 → 每5分钟自动导航到成绩页.
"""

import json
import sys
import time
import hashlib
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

# ============================================================
# 路径
# ============================================================

SCRIPT_DIR    = Path(__file__).resolve().parent
CONFIG_PATH   = SCRIPT_DIR / "config.json"
SNAPSHOT_PATH = SCRIPT_DIR / "grade_snapshot.json"
HISTORY_PATH  = SCRIPT_DIR / "grade_history.log"
MONITOR_LOG   = SCRIPT_DIR / "monitor.log"

# ============================================================
# 日志
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(MONITOR_LOG, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("grade_monitor")

# ============================================================
# 配置
# ============================================================

DEFAULT_CONFIG = {
    "webvpn_base": "https://webvpn.zzuli.edu.cn",
    "check_interval_seconds": 300,
    "max_retry_on_failure": 3,
    "notify": {"desktop": True, "sound": True},
    "parse": {
        "table_selector": "table",
        "row_selector":   "tr",
        "columns":  ["序号", "课程名称", "学分", "总学时", "类别", "修读性质", "考核方式", "平时成绩", "期末成绩", "成绩", "备注"],
        "col_index": [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 13],
    },
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        merged = {**DEFAULT_CONFIG, **user_cfg}
        merged["notify"] = {**DEFAULT_CONFIG["notify"], **user_cfg.get("notify", {})}
        merged["parse"]  = {**DEFAULT_CONFIG["parse"],  **user_cfg.get("parse", {})}
        return merged
    else:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        log.info(f"已生成配置模板: {CONFIG_PATH}")
        sys.exit(0)


# ============================================================
# 通知
# ============================================================

def desktop_notify(title: str, message: str):
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=10, threaded=True)
    except ImportError:
        try:
            import subprocess
            subprocess.run([
                "powershell", "-NoProfile", "-Command",
                f'[Windows.UI.Notifications.ToastNotificationManager]'
                f'::CreateToastNotifier("GradeMonitor").Show('
                f'[Windows.UI.Notifications.ToastNotification]::new('
                f'[Windows.UI.Notifications.ToastNotificationManager]'
                f'::GetTemplateContent('
                f'[Windows.UI.Notifications.ToastTemplateType]::ToastText02))'
            ], capture_output=True, timeout=10)
        except Exception:
            pass


def sound_alert():
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except ImportError:
        pass


def notify(cfg: dict, title: str, message: str):
    if cfg["notify"].get("desktop", True):
        desktop_notify(title, message)
    if cfg["notify"].get("sound", True):
        sound_alert()
    wechat_cfg = cfg["notify"].get("wechat", {})
    if wechat_cfg.get("enabled") and wechat_cfg.get("sendkey"):
        _wechat_push(wechat_cfg["sendkey"], title, message)


def _wechat_push(sendkey: str, title: str, message: str):
    """Server酱 微信推送"""
    try:
        import requests as req
        resp = req.post(
            f"https://sctapi.ftqq.com/{sendkey}.send",
            data={"title": title, "desp": message},
            timeout=10,
        )
        if resp.status_code == 200:
            log.info("微信推送已发送")
        else:
            log.warning(f"微信推送失败: {resp.status_code}")
    except Exception as e:
        log.warning(f"微信推送异常: {e}")


# ============================================================
# 辅助: Playwright 安全点击
# ============================================================

def _safe_click(page, text, exact=False, timeout=5000):
    """安全点击: 查找文本并点击, 返回是否成功"""
    try:
        el = page.get_by_text(text, exact=exact).first
        if el.count() == 0:
            return False
        el.click(timeout=timeout)
        return True
    except Exception:
        return False


def _find_and_click_input(page, value_text):
    """查找 value 包含指定文本的 input 并点击"""
    try:
        inputs = page.locator("input")
        for i in range(min(inputs.count(), 50)):
            val = inputs.nth(i).get_attribute("value") or ""
            if value_text in val:
                inputs.nth(i).click()
                return True
    except Exception:
        pass
    return False


# ============================================================
# 浏览器驱动
# ============================================================

class BrowserDriver:

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.base = cfg["webvpn_base"].rstrip("/")
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.grade_tab = None

    def start(self):
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=False)
        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        self.page = self.context.new_page()

    # ---------- 登录 ----------

    def login(self) -> bool:
        from playwright.sync_api import TimeoutError as PwTimeout

        if not self.browser:
            self.start()

        login_url = f"{self.base}/login?cas_login=true"
        log.info("正在打开登录页...")
        self.page.goto(login_url, wait_until="domcontentloaded")

        log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log.info("📱 请用手机扫码登录 (3分钟超时)")
        log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        try:
            self.page.wait_for_url(
                lambda u: "homes.action" in u
                    or "login" not in u.lower().split("/")[-1],
                timeout=180_000,
            )
        except PwTimeout:
            log.error("扫码超时")
            return False

        self.page.wait_for_timeout(2000)
        log.info(f"✅ 登录成功")
        return True

    # ---------- 登录态检测 ----------

    def check_login_state(self) -> bool:
        try:
            self.page.goto(self.base, wait_until="domcontentloaded", timeout=15000)
            self.page.wait_for_timeout(1000)

            # 检测弹窗
            try:
                dialog = self.page.wait_for_event("dialog", timeout=3000)
                msg = dialog.message
                dialog.dismiss()
                if "失效" in msg or "登录" in msg:
                    log.warning(f"会话过期弹窗: {msg}")
                    return False
            except Exception:
                pass

            if "homes.action" in (self.page.url or ""):
                log.warning("会话过期: 重定向到登录页")
                return False

            return True
        except Exception as e:
            log.warning(f"登录态检测异常: {e}")
            return False

    # ---------- 点击导航到成绩页 ----------

    def navigate_to_grades(self) -> Optional[str]:
        """智能导航: 优先复用已有标签页, 失败走完整流程"""
        if self.grade_tab and self._try_quick_search():
            return self._collect_all_html()
        log.info('🔄 快速路径失败, 走完整导航...')
        return self._full_navigate()

    def _try_quick_search(self) -> bool:
        """快速: 在已有成绩标签页直接点检索"""
        try:
            url = self.grade_tab.url
            if not url or 'about:blank' in url:
                return False
            log.info('🚀 快速路径: 直接检索...')
            return self._click_search_btn(self.grade_tab)
        except Exception:
            return False

    def _full_navigate(self) -> Optional[str]:
        """完整导航: VPN门户→教务→学业成绩→检索"""
        from playwright.sync_api import TimeoutError as PwTimeout

        # Step 1
        log.info('📍 步骤1: VPN门户 → 教务系统')
        try:
            self.page.goto(self.base, wait_until='networkidle', timeout=30000)
            self.page.wait_for_timeout(2000)
            log.info(f'  当前页面: {self.page.title()}')

            clicked = False
            for keyword in ['本科生教务管理', '教务系统', '教务']:
                try:
                    link = self.page.get_by_text(keyword, exact=False).first
                    if link.count() > 0:
                        log.info(f'  找到: {link.inner_text()[:40]}')
                        with self.context.expect_page(timeout=10000) as info:
                            link.click()
                        self.grade_tab = info.value
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                log.error('未找到教务系统入口!')
                self.page.screenshot(path=str(SCRIPT_DIR / 'debug_portal.png'))
                return None
            log.info('✅ 教务系统已在新标签页打开')
        except Exception as e:
            log.error(f'步骤1失败: {e}')
            return None

        # Step 2
        log.info('📍 步骤2: 点击学业成绩...')
        try:
            self.grade_tab.wait_for_load_state('networkidle', timeout=30000)
            self.grade_tab.wait_for_timeout(2000)
            log.info(f'  当前页面: {self.grade_tab.title()}')

            for txt in ['学业成绩', '查看成绩', '成绩']:
                if _safe_click(self.grade_tab, txt, exact=(txt == '学业成绩')):
                    log.info(f'  点击了: {txt}')
                    self.grade_tab.wait_for_load_state('networkidle', timeout=30000)
                    self.grade_tab.wait_for_timeout(2000)
                    log.info('✅ 已进入成绩查询页面')
                    break
        except Exception as e:
            log.warning(f'步骤2异常: {e}')

        # Step 3
        self._click_search_btn(self.grade_tab)
        return self._collect_all_html()

    def _click_search_btn(self, page) -> bool:
        """在指定页面iframe中点击检索并等数据"""
        log.info('📍 点击检索按钮...')
        try:
            page.wait_for_load_state('networkidle', timeout=15000)
            page.wait_for_timeout(1500)

            clicked = False
            for frame in page.frames:
                url = frame.url
                if 'xscj' not in url and 'stuckcj' not in url:
                    continue
                for sel in ['#btnQry', 'input[value=检索]', 'input[name=btnQry]']:
                    btn = frame.locator(sel).first
                    if btn.count() > 0:
                        log.info(f'  找到检索按钮: {sel}')
                        btn.click()
                        clicked = True
                        break
                if clicked:
                    break

            if not clicked:
                log.info('未找到检索按钮')
                return False

            log.info('  检索已点击, 等待数据...')
            page.wait_for_timeout(3000)
            try:
                page.wait_for_load_state('networkidle', timeout=30000)
            except Exception:
                pass
            try:
                page.wait_for_selector('text=/\[\d+\]|综合成绩/', timeout=10000)
                log.info('✅ 成绩数据已加载')
            except Exception:
                pass
            return True
        except Exception as e:
            log.warning(f'点击检索异常: {e}')
            return False

    def _collect_all_html(self) -> str:
        """
        page.frames 已包含所有嵌套 frame (Playwright 自动展平).
        数据在 frmReport frame 中.
        """
        frames = self.grade_tab.frames
        log.info(f"  共 {len(frames)} 个 frame")

        # 列出所有 frame 信息
        for f in frames:
            log.info(f"    frame: name='{f.name}' url={f.url[:100] if f.url else 'None'}")

        # 优先找 frmReport
        for f in frames:
            if f.name == "frmReport" or "frmReport" in (f.url or ""):
                try:
                    html = f.content()
                    log.info(f"  frmReport: {len(html)} bytes")
                    return html
                except Exception as e:
                    log.warning(f"  frmReport 获取失败: {e}")

        # 找包含成绩关键词的
        for f in frames:
            try:
                html = f.content()
                if "综合成绩" in html or "成绩等级" in html:
                    log.info(f"  成绩frame: {len(html)} bytes")
                    return html
            except Exception:
                continue

        # 兜底: 主页
        return self.grade_tab.content()

    # ---------- 关闭 ----------

    def close(self):
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass


# ============================================================
# 成绩解析
# ============================================================

def _debug_table_rows(html: str):
    """调试: 打印表格行结构, 帮助确定列索引"""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    for ti, table in enumerate(tables):
        rows = table.find_all("tr")
        # 找包含课程代码的行
        for ri, row in enumerate(rows):
            cells = row.find_all(["td", "th"])
            row_text = " | ".join(c.get_text(strip=True)[:20] for c in cells)
            if "[" in row_text or "课程" in row_text or "成绩" in row_text:
                log.info(f"  TABLE[{ti}] ROW[{ri}] ({len(cells)}列): {row_text[:200]}")
                if "[" in row_text:
                    # 打印每列的详细内容
                    for ci, c in enumerate(cells):
                        log.info(f"    col[{ci}] = '{c.get_text(strip=True)[:40]}'")


def parse_grades(html: str, cfg: dict) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    pc = cfg.get("parse", {})
    columns = pc.get("columns", [])
    col_idx = pc.get("col_index", [])

    # ---- 调试: 打印原始 table 行结构 ----
    _debug_table_rows(html)

    # ---- 方法1: 找传统 <table> ----
    tables = soup.find_all("table")
    for t in tables:
        txt = t.get_text()
        if "课程" in txt and ("成绩" in txt or "学分" in txt):
            return _parse_table_rows(t, columns, col_idx, pc.get("row_selector", "tr"))

    # ---- 方法2: 找 div 模拟的表格 (青果常见: div.datagrid) ----
    for cls_pattern in [".datagrid", ".grid", "#grid", "#dataGrid", ".ui-jqgrid"]:
        container = soup.select_one(cls_pattern)
        if container:
            rows = container.find_all("tr") or container.select("[class*=row]")
            if rows:
                return _parse_table_rows(container, columns, col_idx, "tr")

    # ---- 方法3: 找所有 <tr> 元素 ----
    all_trs = soup.find_all("tr")
    if all_trs:
        # 找一个包含成绩的容器
        for tr in all_trs:
            txt = tr.get_text()
            if "综合成绩" in txt or "成绩等级" in txt:
                # 找到表头行, 往上找父table
                parent = tr.find_parent("table") or tr.find_parent("tbody")
                if parent:
                    return _parse_table_rows(parent, columns, col_idx, "tr")
                # 如果没父table, 用所有tr
                break
        # 用所有 tr
        wrapper = soup.new_tag("div")
        for tr in all_trs:
            wrapper.append(tr)
        return _parse_table_rows(wrapper, columns, col_idx, "tr")

    # ---- 方法4: 纯文本正则提取 ----
    log.warning("未找到表格结构, 尝试正则提取...")
    return _parse_by_regex(soup.get_text(), columns)


def _parse_table_rows(container, columns: list, col_idx: list, row_sel: str) -> list[dict]:
    """从表格容器中提取行数据"""
    rows = container.select(row_sel) if row_sel != "tr" else container.find_all("tr")
    results = []
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < max(col_idx, default=0) + 1:
            continue
        item = {}
        for name, idx in zip(columns, col_idx):
            if idx < len(cells):
                item[name] = cells[idx].get_text(strip=True)
        name = item.get("课程名称", "")
        if not name or name in ("课程/环节", "课程名称", "课程"):
            continue
        if any(item.values()):
            results.append(item)
    return results


def _parse_by_regex(text: str, columns: list) -> list[dict]:
    """正则兜底: 匹配 [课程代码]课程名 模式"""
    import re
    results = []
    # 匹配 [XXXXX]课程名 后面跟的数字
    pattern = re.compile(r'\[(\d+)\](\S+?)\s+([\d.]+)\s+(\S+)')
    for m in pattern.finditer(text):
        item = {
            "序号": "",
            "课程名称": f"[{m.group(1)}]{m.group(2)}",
            "学分": m.group(3),
            "成绩等级": m.group(4),
        }
        results.append(item)
    return results


# ============================================================
# 快照 & 历史 & 对比
# ============================================================

def load_snapshot() -> Optional[dict]:
    if SNAPSHOT_PATH.exists():
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_snapshot(grades: list[dict]):
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "count": len(grades),
        "grades": grades,
        "fingerprint": hashlib.sha256(
            json.dumps(grades, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
    }
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def append_history(change_type: str, details: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{now}] [{change_type}]\n{details}\n{'=' * 60}\n")


def compare_grades(old: list[dict], new: list[dict]) -> tuple[bool, str]:
    if not old:
        return bool(new), f"首次获取: {len(new)} 门课程"

    old_map = {g.get("课程名称", ""): g for g in old}
    new_map = {g.get("课程名称", ""): g for g in new}

    added   = [n for n in new if n["课程名称"] not in old_map]
    removed = [o for o in old if o["课程名称"] not in new_map]
    changed = []

    for name, new_g in new_map.items():
        old_g = old_map.get(name)
        if old_g:
            diffs = {}
            for k, v in new_g.items():
                if old_g.get(k) != v:
                    diffs[k] = f"{old_g.get(k)} -> {v}"
            if diffs:
                changed.append({"课程名称": name, "变化": diffs})

    has_change = bool(added or removed or changed)
    lines = []
    if added:
        lines.append(f"\n新 新增 {len(added)} 门:")
        for g in added:
            lines.append(f"  + {g}")
    if removed:
        lines.append(f"\n移除 {len(removed)} 门:")
        for g in removed:
            lines.append(f"  - {g}")
    if changed:
        lines.append(f"\n变化 {len(changed)} 门:")
        for c in changed:
            lines.append(f"  * {c['课程名称']}: {c['变化']}")
    if not has_change:
        lines.append("无变化")
    return has_change, "\n".join(lines)


# ============================================================
# 主循环
# ============================================================

paused_event = threading.Event()
paused_event.set()
pause_reason = ""
force_check_event = threading.Event()


def input_listener():
    global pause_reason
    while True:
        try:
            cmd = input().strip()
            if cmd == "" and not paused_event.is_set():
                log.info("恢复指令 → 重新扫码登录...")
                paused_event.set()
                pause_reason = ""
            elif cmd.lower() == "aaa":
                log.info("⚡ 立即检查")
                force_check_event.set()
        except (EOFError, KeyboardInterrupt):
            break


def check_once(cfg: dict, driver: BrowserDriver) -> bool:
    # 1. 登录态检测
    if not driver.check_login_state():
        return False

    # 2. 点击导航获取成绩页
    html = driver.navigate_to_grades()
    if html is None:
        log.error("导航获取成绩页失败")
        return True  # 网络/页面结构问题, 下轮重试

    # 3. 解析
    grades = parse_grades(html, cfg)
    if not grades:
        log.warning("未解析到成绩, 保存 debug_last_page.html 供分析")
        with open(SCRIPT_DIR / "debug_last_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        return True

    log.info(f"解析到 {len(grades)} 门课程")

    # 4. 对比
    old_snapshot = load_snapshot()
    old_grades = old_snapshot["grades"] if old_snapshot else []
    has_change, report = compare_grades(old_grades, grades)

    # 5. 结果
    if has_change:
        log.info(f"成绩变化!\n{report}")
        append_history("CHANGE", report)
        notify(cfg, "成绩变化!", report[:200])
        change_file = SCRIPT_DIR / f"change_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(change_file, "w", encoding="utf-8") as f:
            f.write(report)
    else:
        log.info("成绩无变化")

    save_snapshot(grades)
    return True


def main_loop(cfg: dict):
    global pause_reason
    driver = BrowserDriver(cfg)

    log.info("━━━ 准备扫码登录 ━━━")
    if not driver.login():
        log.error("登录失败"); sys.exit(1)

    threading.Thread(target=input_listener, daemon=True).start()

    interval = cfg["check_interval_seconds"]
    log.info(f"监控开始 (每 {interval//60} 分钟), 输入 aaa 立即检查")

    try:
        while True:
            paused_event.wait()

            ok = check_once(cfg, driver)

            if not ok:
                pause_reason = "登录态已过期"
                log.warning(f"{pause_reason}")
                notify(cfg, "成绩监控 - 登录失效!",
                       "会话已过期, 按 Enter 重新扫码")
                append_history("SESSION_EXPIRED", pause_reason)
                paused_event.clear()

                while not paused_event.is_set():
                    time.sleep(30)
                    log.warning(f"等待手动扫码... ({pause_reason})")

                if not driver.login():
                    log.error("重新登录失败")
                    paused_event.clear()
                    continue
                log.info("重新登录成功")

            # 等待下一轮
            log.info(f"下一轮: {interval//60} 分钟后")
            force_check_event.clear()
            for _ in range(interval):
                if not paused_event.is_set():
                    break
                if force_check_event.is_set():
                    log.info("⚡ 立即检查...")
                    break
                time.sleep(1)

    except KeyboardInterrupt:
        log.info("退出")
    finally:
        driver.close()
        log.info("已停止")


def main():
    cfg = load_config()
    main_loop(cfg)


if __name__ == "__main__":
    main()
