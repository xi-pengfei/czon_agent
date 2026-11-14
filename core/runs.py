"""Single-process bounded execution, durable account event feed, reconnectable runs.

Execution is deliberately never resumed automatically after a restart: tools may
have committed external side effects. Run one WebUI process per database.
"""
from contextlib import contextmanager
import fcntl
import json
import sqlite3
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

TERMINAL = {'completed', 'stopped', 'failed', 'interrupted'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


class RunManager:
    def __init__(self, db_path, max_workers=3, per_owner=3, max_pending=32):
        if not (1 <= max_workers <= 16 and 1 <= per_owner <= max_workers and 1 <= max_pending <= 256):
            raise ValueError("Invalid run concurrency configuration")
        self.db_path = str(db_path)
        self._lease = open(self.db_path + '.runs.lock', 'a')
        try:
            fcntl.flock(self._lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lease.close()
            raise RuntimeError('该数据库已有任务执行器，请保持一个 WebUI 进程；不要增加 Uvicorn workers')
        self._lease_cleanup = weakref.finalize(self, self._lease.close)
        self.closed = False
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='czon-run')
        self.max_workers, self.per_owner, self.max_pending = max_workers, per_owner, max_pending
        self.pending = {}
        self.running = {}
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, session_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, snapshot TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS run_owner ON agent_runs(owner);
                CREATE TABLE IF NOT EXISTS agent_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL,
                    run_id TEXT NOT NULL, event TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS event_owner_seq ON agent_events(owner, seq);
            ''')
            rows = db.execute('SELECT snapshot FROM agent_runs').fetchall()
        for row in rows:
            run = json.loads(row[0])
            if run['status'] not in TERMINAL:
                self.emit(run['id'], 'agent_interrupted', {'message': '服务已重启，任务结果待核实，请勿重复执行业务。'})

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, run_id, owner=None):
        with self.connect() as db:
            row = db.execute('SELECT owner,snapshot FROM agent_runs WHERE id=?', (run_id,)).fetchone()
        if not row or (owner is not None and row['owner'] != owner):
            return None
        return json.loads(row['snapshot'])

    def snapshot(self, owner):
        # Cursor and snapshots must describe the same instant.
        with self.lock, self.connect() as db:
            rows = db.execute("SELECT snapshot FROM agent_runs WHERE owner=? AND (json_extract(snapshot, '$.status') IN ('queued','running') OR id IN (SELECT id FROM agent_runs WHERE owner=? ORDER BY rowid DESC LIMIT 200)) ORDER BY rowid DESC", (owner, owner)).fetchall()
            cursor = db.execute('SELECT COALESCE(MAX(seq),0) FROM agent_events WHERE owner=?', (owner,)).fetchone()[0]
        return {'runs': [json.loads(r[0]) for r in rows], 'cursor': cursor}

    def session_runs(self, sid, owner):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(
                'SELECT snapshot FROM agent_runs WHERE session_id=? AND owner=? ORDER BY rowid', (sid, owner))]

    def events(self, owner, after=0, run_id=None):
        with self.connect() as db:
            query = 'SELECT * FROM agent_events WHERE owner=? AND seq>?'
            args = [owner, after]
            if run_id:
                query += ' AND run_id=?'
                args.append(run_id)
            rows = db.execute(query + ' ORDER BY seq LIMIT 256', args).fetchall()
        return [{**dict(r), 'data': json.loads(r['data'])} for r in rows]

    def submit(self, run, fingerprint, work, prepare):
        with self.lock:
            if self.closed:
                raise OverflowError("服务正在停止，请稍后再试")
            with self.connect() as db:
                old = db.execute('SELECT owner,fingerprint,snapshot FROM agent_runs WHERE id=?', (run['id'],)).fetchone()
            if old:
                if old['owner'] != run['owner'] or old['fingerprint'] != fingerprint:
                    raise ValueError('任务标识已被其他请求使用')
                return json.loads(old['snapshot'])
            if len(self.pending) + len(self.running) >= self.max_pending:
                raise OverflowError('任务队列已满，请稍后再试')
            if sum(r['owner'] == run['owner'] for r, _, _ in self.pending.values()) >= 8:
                raise OverflowError('当前账号排队任务过多，请稍后再试')
            prepare()
            run.update(status='queued', created_at=now(), reply='', steps=[], artifacts=[], progress='已排队，等待执行')
            with self.connect() as db:
                db.execute('INSERT INTO agent_runs VALUES(?,?,?,?,?)', (run['id'], run['owner'], run['session_id'], fingerprint, json.dumps(run, ensure_ascii=False)))
            self.emit(run['id'], 'run_created', run)
            stop = threading.Event()
            self.pending[run['id']] = (run, work, stop)
            self._schedule()
            return self.get(run['id'])

    def _schedule(self):
        for rid, (run, work, stop) in list(self.pending.items()):
            if len(self.running) >= self.max_workers:
                break
            if any(r['session_id'] == run['session_id'] for r, _ in self.running.values()):
                continue
            if sum(r['owner'] == run['owner'] for r, _ in self.running.values()) >= self.per_owner:
                continue
            del self.pending[rid]
            self.running[rid] = (run, stop)
            self.pool.submit(self._execute, run, work, stop)

    def _execute(self, run, work, stop):
        try:
            self.emit(run['id'], 'agent_start', {'provider': run['provider']})
            work(stop, lambda event, data: self.emit(run['id'], event, data))
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Run failed: %s', run['id'])
            self.emit(run['id'], 'agent_error', {'error': '任务执行异常，结果待核实，请勿重复执行业务。'})
        finally:
            with self.lock:
                self.running.pop(run['id'], None)
                self._schedule()

    def emit(self, rid, event, data):
        with self.lock, self.connect() as db:
            row = db.execute('SELECT snapshot FROM agent_runs WHERE id=?', (rid,)).fetchone()
            if not row:
                return
            run = json.loads(row[0])
            if event == 'agent_start':
                run.update(status='running', started_at=now(), progress='正在处理你的请求')
            elif event == 'assistant_delta':
                run['reply'] += data['text']
            elif event in {'tool_start', 'tool_progress', 'tool_result', 'confirmation_required'}:
                steps = run['steps']
                index = next((i for i, s in enumerate(steps) if data.get('id') and s.get('id') == data['id']), None)
                step = dict(steps[index]) if index is not None else {}
                if event == 'tool_progress':
                    step.update({k: v for k, v in data.items() if k != 'text'})
                    step['progress'] = (step.get('progress', '') + data.get('text', ''))[-30000:]
                else:
                    step.update(data)
                if index is None:
                    steps.append(step)
                else:
                    steps[index] = step
                run['steps'] = steps[-100:]
                run['progress'] = '需要确认才能继续' if event == 'confirmation_required' else ('正在执行业务操作' if event == 'tool_start' else '正在整理执行结果')
            elif event == 'agent_done':
                run.update(status='completed', reply=data.get('reply', ''), artifacts=data.get('artifacts', []), metrics=data.get('metrics', {}), progress='处理完成')
            elif event in {'agent_stopped', 'agent_timeout', 'agent_error', 'agent_interrupted'}:
                run['status'] = {'agent_stopped': 'stopped', 'agent_interrupted': 'interrupted'}.get(event, 'failed')
                run['error'] = data.get('error') or data.get('message', '任务未完成')
                run['progress'] = run['error']
            elif event == 'run_stopping':
                run['progress'] = '正在停止，等待当前操作结束'
            if run['status'] in TERMINAL:
                run['finished_at'] = now()
            encoded = json.dumps(data, ensure_ascii=False)
            db.execute('UPDATE agent_runs SET snapshot=? WHERE id=?', (json.dumps(run, ensure_ascii=False), rid))
            db.execute('INSERT INTO agent_events(owner,run_id,event,data) VALUES(?,?,?,?)', (run['owner'], rid, event, encoded))

    def stop(self, rid, owner, sid):
        with self.lock:
            run = self.get(rid, owner)
            if not run or run['session_id'] != sid:
                return False
            if rid in self.pending:
                self.pending.pop(rid)
                self.emit(rid, 'agent_stopped', {'message': '已取消排队'})
            elif rid in self.running:
                self.running[rid][1].set()
                self.emit(rid, 'run_stopping', {})
            return True

    def busy(self, sid):
        with self.lock:
            return any(r['session_id'] == sid for r, _ in self.running.values()) or any(r['session_id'] == sid for r, _, _ in self.pending.values())

    def close(self):
        with self.lock:
            self.closed = True
            for rid in list(self.pending):
                self.emit(rid, 'agent_interrupted', {'message': '服务正在停止，排队任务未执行'})
            self.pending.clear()
            for _, stop in self.running.values():
                stop.set()
        self.pool.shutdown(wait=True)
        if not self._lease.closed:
            fcntl.flock(self._lease, fcntl.LOCK_UN)
            self._lease.close()

    def delete_session(self, sid, owner):
        with self.lock, self.connect() as db:
            if self.busy(sid):
                raise ValueError('请先停止该会话的运行及排队任务')
            db.execute('DELETE FROM agent_events WHERE run_id IN (SELECT id FROM agent_runs WHERE session_id=? AND owner=?)', (sid, owner))
            db.execute('DELETE FROM agent_runs WHERE session_id=? AND owner=?', (sid, owner))
            db.execute('INSERT INTO agent_events(owner,run_id,event,data) VALUES(?,?,?,?)', (owner, '', 'session_deleted', json.dumps({'session_id': sid})))
