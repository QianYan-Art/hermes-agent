"""固定作品包、浏览器草稿与逐次确认的发布操作。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import stat
import time
from urllib.parse import parse_qs, urlsplit
import uuid

from releases import ReleaseError, ReleaseStore

LOGGER = logging.getLogger("douyin_content")
HOME_URL = "https://creator.douyin.com/creator-micro/home"
UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
MANAGE_URL = "https://creator.douyin.com/creator-micro/content/manage"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{32}\Z")
ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
JOB_PATTERN = re.compile(r"[a-f0-9]{32}\Z")
PLAN_TTL = 15 * 60
JOB_TIMEOUT = 10 * 60
PAGE_OPERATION_TIMEOUT = 40


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def response(state, message, **fields):
    return {"ok": state not in {"unavailable", "page_error", "needs_attention", "account_mismatch", "verification_required", "login_required", "unknown"},
            "state": state, "message": message, **fields}


def validate_request(value):
    if not isinstance(value, dict) or not isinstance(value.get("action"), str):
        raise ValueError("作品请求无效")
    action = value["action"]
    allowed = {
        "list": {"action"}, "metrics": {"action"},
        "prepare": {"action", "release_id", "title", "description"},
        "draft": {"action", "token"}, "publish": {"action", "token"},
        "job": {"action", "job_id"},
    }
    if action not in allowed or set(value) - allowed[action]:
        raise ValueError("作品请求包含未支持的操作或字段")
    if action == "prepare":
        if not isinstance(value.get("release_id"), str) or not ID_PATTERN.fullmatch(value["release_id"]):
            raise ValueError("作品编号无效")
        if "title" in value and (not isinstance(value["title"], str) or not 1 <= len(value["title"].strip()) <= 30):
            raise ValueError("标题须为1到30个字符")
        if "title" in value and any(char in value["title"] for char in "\r\n\0"):
            raise ValueError("标题不能包含换行或空字符")
        if "description" in value and (not isinstance(value["description"], str) or len(value["description"]) > 1000):
            raise ValueError("简介不能超过1000个字符")
        if "\0" in value.get("description", ""):
            raise ValueError("简介不能包含空字符")
    if action in {"draft", "publish"} and (not isinstance(value.get("token"), str) or not TOKEN_PATTERN.fullmatch(value["token"])):
        raise ValueError("准备令牌无效")
    if action == "job" and (not isinstance(value.get("job_id"), str) or not JOB_PATTERN.fullmatch(value["job_id"])):
        raise ValueError("任务编号无效")
    return dict(value)


def _directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("作品状态目录不安全")
    path.chmod(0o700)
    return path


def _read_json(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
        raise ValueError("作品状态文件不安全")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("作品状态文件不安全")
        raw = stream.read(65537)
    if len(raw.encode("utf-8")) > 65536:
        raise ValueError("作品状态文件过大")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("作品状态无效")
    return value


def _write_json(path, value):
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(6))
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            temporary.chmod(0o600)
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        if os.name == "posix":
            descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _safe_editor_url(value):
    url = urlsplit(value)
    return url.scheme == "https" and url.netloc == "creator.douyin.com" and url.path.startswith("/creator-micro/content/")


class ContentManager:
    def __init__(self, browser, browser_lock):
        self.browser = browser
        self.browser_lock = browser_lock
        self.store = ReleaseStore(browser.config.data_dir)
        self.plan_dir = _directory(browser.config.data_dir / "content-plans")
        self.job_dir = _directory(browser.config.data_dir / "content-jobs")
        self.jobs = {}
        self.tasks = {}
        self.state_lock = asyncio.Lock()
        for path in sorted(self.job_dir.glob("*.json"))[-1000:]:
            if not JOB_PATTERN.fullmatch(path.stem):
                continue
            job = _read_json(path)
            if job.get("state") == "in_progress":
                job.update(state="needs_attention", phase="结果待核实", message="服务曾中断；操作结果不明，禁止自动重复上传或发布。", updated_at=utc_now())
                _write_json(path, job)
            self.jobs[path.stem] = job

    def _save_job(self, job):
        job["updated_at"] = utc_now()
        self.jobs[job["job_id"]] = job
        _write_json(self.job_dir / (job["job_id"] + ".json"), job)

    def _job_response(self, job):
        public = {key: job[key] for key in ("job_id", "action", "release_id", "state", "phase", "updated_at", "message")}
        extra = {"ui": job["ui"]} if job.get("state") == "needs_attention" and "ui" in job else {}
        return response(job["state"], job["message"], job=public, **extra)

    def _plan(self, token):
        plan = _read_json(self.plan_dir / (token + ".json"))
        if plan["expires_unix"] < time.time():
            raise ValueError("准备令牌已过期，请重新准备作品")
        release = self.store.load(plan["release_id"])
        if release["video_sha256"] != plan["video_sha256"] or plan["account"] != self.browser.config.expected_account:
            raise ValueError("作品内容或目标账号发生变化，请重新准备")
        return plan, release

    async def _account_page(self):
        page = await self.browser._page()
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        snapshot = await self.browser._wait_for_login_ui(page, wait_for_qr=False)
        # 复用登录服务现有的账号与挑战判别，不将 Cookie 存在视为授权。
        import service
        state = service.classify_page(snapshot, self.browser.config.expected_account)
        if state != "logged_in":
            raise ValueError("账号未确认或需要人工验证，停止作品操作：" + state)
        return page

    async def _ui(self, page):
        result = await page.evaluate("""() => ({
          buttons:Array.from(document.querySelectorAll('button,[role="button"]')).filter(e=>e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0).map(e=>(e.innerText||e.getAttribute('aria-label')||'').trim()).filter(Boolean).slice(0,60),
          inputs:Array.from(document.querySelectorAll('input')).map(e=>({type:e.type,accept:e.accept,placeholder:e.placeholder})).slice(0,30),
          editable:Array.from(document.querySelectorAll('[contenteditable="true"],textarea')).map(e=>({placeholder:e.getAttribute('data-placeholder')||e.getAttribute('placeholder')||'',role:e.getAttribute('role')||''})).slice(0,20),
          labels:Array.from(document.querySelectorAll('label')).map(e=>e.innerText.trim()).filter(Boolean).slice(0,30),
          text_tail:document.body.innerText.slice(-4000)
        })""")
        expected = self.browser.config.expected_account
        if expected:
            result["text_tail"] = result["text_tail"].replace(expected, "[预期账号]")
        result["page"] = "https://creator.douyin.com" + urlsplit(page.url).path
        return result

    async def process(self, request):
        try:
            request = validate_request(request)
            action = request["action"]
            if action == "list":
                return response("ready", "仅列出已校验并暂存到服务器的作品。", releases=self.store.list_releases())
            if action == "job":
                job = self.jobs.get(request["job_id"])
                if job is None:
                    raise ValueError("任务不存在")
                return self._job_response(job)
            if action in {"draft", "publish"}:
                return await self._start_job(action, request["token"])
            if self.browser_lock.locked():
                return response("needs_attention", "浏览器正在处理其他任务，请先查询任务状态。")
            async with self.browser_lock:
                if action == "prepare":
                    return await asyncio.wait_for(self._prepare(request), timeout=PAGE_OPERATION_TIMEOUT)
                return await asyncio.wait_for(self._metrics(), timeout=PAGE_OPERATION_TIMEOUT)
        except FileNotFoundError:
            return response("needs_attention", "作品、任务或准备令牌不存在，请先列出并准备作品。")
        except (ValueError, ReleaseError) as exc:
            return response("needs_attention", str(exc))
        except Exception as exc:
            LOGGER.warning("作品操作失败，异常类型：%s", type(exc).__name__)
            return response("page_error", "作品操作失败，请检查服务或页面；没有自动重试。")

    async def _prepare(self, request):
        release = self.store.load(request["release_id"])
        title = request.get("title", release["title"]).strip()
        description = request.get("description", release["description"])
        page = await self._account_page()
        await page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)
        ui = await self._ui(page)
        token = secrets.token_urlsafe(24)
        plan = {"token": token, "release_id": release["release_id"], "title": title,
                "description": description, "ai_generated": True, "video_sha256": release["video_sha256"],
                "account": self.browser.config.expected_account, "expires_unix": time.time() + PLAN_TTL,
                "expires_at": datetime.fromtimestamp(time.time() + PLAN_TTL, timezone.utc).isoformat()}
        stable = {key: plan[key] for key in ("release_id", "title", "description", "ai_generated", "video_sha256", "account")}
        plan["fingerprint"] = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        _write_json(self.plan_dir / (token + ".json"), plan)
        public = {key: plan[key] for key in ("token", "release_id", "title", "description", "ai_generated", "video_sha256", "expires_at")}
        return response("ready", "作品已准备，尚未上传或发布。需要公开发布时，须先保存草稿，再由本人私聊发送：确认发布 " + token,
                        plan=public, ui=ui)

    async def _start_job(self, action, token):
        async with self.state_lock:
            plan, release = self._plan(token)
            for job in self.jobs.values():
                if job.get("fingerprint") == plan["fingerprint"] and job.get("action") == action:
                    if (action == "draft" and job.get("root_resume_authorized") is True
                            and job.get("state") == "needs_attention" and not job.get("commit_attempted")):
                        if any(other.get("state") == "in_progress" for other in self.jobs.values()):
                            raise ValueError("已有作品任务在进行，暂不恢复")
                        job.pop("root_resume_authorized")
                        job.update(state="in_progress", phase="恢复保存前任务", message="运维已授权恢复，尚未尝试过保存或发布。")
                        self._save_job(job)
                        task = asyncio.create_task(self._run(job, plan, release))
                        self.tasks[job["job_id"]] = task
                        task.add_done_callback(lambda _task: self.tasks.pop(job["job_id"], None))
                    return self._job_response(job)
            if action == "publish" and not any(j.get("fingerprint") == plan["fingerprint"] and j.get("state") == "draft_saved" for j in self.jobs.values()):
                raise ValueError("须先成功保存这份物料的草稿，不能直接公开发布")
            if any(j.get("state") == "in_progress" for j in self.jobs.values()):
                raise ValueError("已有作品任务在进行，请等待并查询原任务")
            job = {"job_id": uuid.uuid4().hex, "action": action, "release_id": release["release_id"],
                   "state": "in_progress", "phase": "排队", "message": "任务已接收，请按任务编号查询，不要重复提交。",
                   "fingerprint": plan["fingerprint"], "created_at": utc_now()}
            self._save_job(job)
            task = asyncio.create_task(self._run(job, plan, release))
            self.tasks[job["job_id"]] = task
            task.add_done_callback(lambda _task: self.tasks.pop(job["job_id"], None))
            return self._job_response(job)

    async def _run(self, job, plan, release):
        try:
            async with self.browser_lock:
                await asyncio.wait_for(self._execute(job, plan, release), timeout=JOB_TIMEOUT)
        except (Exception, asyncio.CancelledError) as exc:
            LOGGER.warning("作品任务停止，异常类型：%s", type(exc).__name__)
            job.update(state="needs_attention", phase="结果待核实", message="操作未确认完成；请人工核查草稿或作品，不要自动重复提交。")
            if not isinstance(exc, asyncio.CancelledError):
                try:
                    context = self.browser._context
                    if context is not None and context.pages:
                        job["ui"] = await self._ui(context.pages[0])
                except Exception:
                    LOGGER.info("未能取得作品页面的受限诊断信息。")
            self._save_job(job)
            if isinstance(exc, asyncio.CancelledError):
                raise

    def _phase(self, job, value):
        job.update(phase=value, message=value)
        self._save_job(job)

    async def _button(self, page, names):
        for name in names:
            target = page.get_by_role("button", name=name, exact=True)
            if await target.count() == 1 and await target.is_visible():
                return target
        raise ValueError("没有唯一可操作的目标按钮")

    async def _fill_metadata(self, page, plan):
        title = page.locator('input[placeholder*="作品标题"],input[placeholder*="填写标题"]')
        await title.wait_for(state="visible", timeout=180000)
        if await title.count() != 1:
            raise ValueError("作品标题输入框不唯一")
        await title.fill(plan["title"])
        description = self._description_field(page)
        if await description.count() != 1:
            raise ValueError("作品简介输入框不唯一")
        await description.fill(plan["description"])

    def _description_field(self, page):
        # 实际编辑页是无 placeholder 的唯一可见 contenteditable。
        return page.locator('[contenteditable="true"]:visible, textarea[placeholder*="简介"]:visible')

    async def _ai_is_selected(self, page):
        checkbox = page.get_by_role("checkbox", name=re.compile(r"^(内容由AI生成|AI生成|声明内容由AI生成)$"))
        if await checkbox.count() == 1 and await checkbox.is_visible() and await checkbox.is_checked():
            return True
        selected = []
        for role in ("option", "radio"):
            candidate = page.get_by_role(role, name="内容由AI生成", exact=True)
            for index in range(min(await candidate.count(), 10)):
                item = candidate.nth(index)
                attribute = "aria-selected" if role == "option" else "aria-checked"
                checked = await item.get_attribute(attribute) == "true"
                if role == "radio" and await item.get_attribute("type") == "radio":
                    checked = await item.is_checked()
                if await item.is_visible() and checked:
                    selected.append(item)
        return len(selected) == 1

    async def _ai_declaration(self, page):
        if await self._ai_is_selected(page):
            return
        option = page.get_by_text("内容由AI生成", exact=True)
        if await option.count() != 1 or not await option.is_visible():
            declaration = page.get_by_text("自主声明", exact=True)
            if await declaration.count() == 1:
                await declaration.click()
        if await option.count() != 1 or not await option.is_visible():
            raise ValueError("AI生成声明控件不可确认")
        checkbox = page.get_by_role("checkbox", name=re.compile(r"^(内容由AI生成|AI生成|声明内容由AI生成)$"))
        if await checkbox.count() == 1 and await checkbox.is_visible():
            await checkbox.check()
        else:
            await option.click()
        # 只接受页面重新显示的选中状态，不把简介中的文字当作平台声明。
        if not await self._ai_is_selected(page):
            raise ValueError("AI生成声明未能确认已选中")

    async def _execute(self, job, plan, release):
        # 再次校验文件，避免排队期间被替换的作品沿用旧确认。
        current = self.store.load(plan["release_id"])
        if current["video_sha256"] != plan["video_sha256"]:
            raise ValueError("待操作作品发生变化")
        page = await self._account_page()
        if job["action"] == "publish":
            await self._publish(page, job, plan)
            return
        self._phase(job, "打开上传页")
        await page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=30000)
        upload = page.locator('input[type="file"][accept*="video"], input[type="file"][accept*=".mp4"]')
        await upload.first.wait_for(state="attached", timeout=15000)
        if await upload.count() != 1:
            raise ValueError("视频上传控件不唯一或未加载")
        self._phase(job, "上传视频")
        await upload.set_input_files(str(current["video_path"]))
        await self._fill_metadata(page, plan)
        self._phase(job, "核对AI生成声明")
        try:
            await self._ai_declaration(page)
            job["ai_declaration_verified"] = True
        except ValueError:
            job["ai_declaration_verified"] = False
            LOGGER.info("草稿中的平台AI声明尚未确认，公开发布仍会强制核验。")
        await page.keyboard.press("Escape")
        self._phase(job, "等待视频处理")
        save = await self._button(page, ("保存草稿", "暂存离开"))
        deadline = time.monotonic() + 300
        while not await save.is_enabled():
            if time.monotonic() > deadline:
                raise TimeoutError("视频处理未完成")
            await asyncio.sleep(2)
        editor_url = page.url
        if not _safe_editor_url(editor_url):
            raise ValueError("编辑页不在允许范围")
        self._phase(job, "保存草稿，结果待确认")
        job["editor_url"] = editor_url
        job["commit_attempted"] = True
        self._save_job(job)
        await save.click()
        dialog = page.get_by_role("dialog").filter(has_text=re.compile("草稿|暂存"))
        if await dialog.count() == 1 and await dialog.is_visible():
            confirm = await self._button(dialog, ("保存草稿", "暂存", "保存并离开", "确定"))
            await confirm.click()
        success = page.get_by_text(re.compile(r"^(草稿保存成功|已保存草稿|草稿已保存|保存草稿成功|已保存至草稿箱|保存成功|暂存成功|已暂存)$"))
        await success.first.wait_for(state="visible", timeout=20000)
        message = "页面已确认草稿保存成功，没有点击正式发布。"
        if not job["ai_declaration_verified"]:
            message += "平台AI声明未确认，正式发布前必须再核验。"
        job.update(state="draft_saved", phase="草稿已保存", message=message)
        self._save_job(job)

    async def _publish(self, page, job, plan):
        previous = next(j for j in self.jobs.values() if j.get("fingerprint") == plan["fingerprint"] and j.get("state") == "draft_saved")
        editor_url = previous.get("editor_url", "")
        identifiers = parse_qs(urlsplit(editor_url).query)
        identified = any(identifiers.get(key) for key in ("draft_id", "item_id", "aweme_id", "video_id", "id"))
        if not _safe_editor_url(editor_url) or urlsplit(editor_url).path.endswith("/upload") or not identified:
            raise ValueError("没有可唯一定位的已存草稿；请人工核对，不重新上传")
        await page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
        title = page.locator('input[placeholder*="作品标题"],input[placeholder*="填写标题"]')
        await title.wait_for(state="visible", timeout=15000)
        if await title.count() != 1 or await title.input_value() != plan["title"]:
            raise ValueError("草稿内容不匹配，不公开发布")
        description = self._description_field(page)
        if await description.count() != 1:
            raise ValueError("草稿简介无法唯一核对，不公开发布")
        actual = await description.input_value() if await description.evaluate("e => e.tagName === 'TEXTAREA'") else await description.inner_text()
        if actual.strip() != plan["description"].strip():
            raise ValueError("草稿简介发生变化，不公开发布")
        await self._ai_declaration(page)
        publish = await self._button(page, ("发布",))
        self._phase(job, "正式发布，结果待确认")
        await publish.click()
        await page.get_by_text(re.compile(r"^(发布成功|作品发布成功|发布成功，正在审核)$")).first.wait_for(state="visible", timeout=30000)
        job.update(state="published", phase="已提交发布", message="页面已确认提交发布；后续审核状态以平台为准。")
        self._save_job(job)

    async def _metrics(self):
        page = await self._account_page()
        fields = await page.evaluate("""() => {
          const labels = ['粉丝总数','总粉丝','获赞总数','总获赞','作品总数','播放量','点赞量','评论量','分享量'];
          const fields = [];
          for (const label of labels) {
            const node = Array.from(document.querySelectorAll('span,div,p')).find(e=>e.children.length===0 && e.innerText.trim()===label);
            if (node) {
              const text = node.parentElement?.innerText?.trim() || '';
              if (text.length < 160) fields.push({label, value:text});
            }
          }
          return fields;
        }""")
        message = "仅返回创作者中心首页当前可见数据，不是官方统计API。" if fields else "当前页面没有可可靠提取的统计字段，不能据此认为数值为零。"
        return response("ready", message, metrics={"source": HOME_URL, "collected_at": utc_now(), "fields": fields})

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
