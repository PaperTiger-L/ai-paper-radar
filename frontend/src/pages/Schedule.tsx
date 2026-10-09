import { useCallback, useEffect, useState } from 'react';
import { api, errorMessage } from '../api';
import type { DigestPreview, JobStatus, RunInfo, ScheduleConfig, Subscriber } from '../types';
import {
  Badge,
  Button,
  Card,
  Field,
  Input,
  Modal,
  PageHeader,
  Select,
  Spinner,
  TableShell,
  Toggle,
  fmtDateTime,
  usePolling,
  useToast,
} from '../ui';

const DAY_OPTIONS = [
  { value: 0, label: '周一' },
  { value: 1, label: '周二' },
  { value: 2, label: '周三' },
  { value: 3, label: '周四' },
  { value: 4, label: '周五' },
  { value: 5, label: '周六' },
  { value: 6, label: '周日' },
];

function DigestPreviewModal({
  subscriberId,
  onClose,
}: {
  subscriberId: number;
  onClose: () => void;
}) {
  const toast = useToast();
  const [preview, setPreview] = useState<DigestPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    api
      .get<DigestPreview>(`/digest/preview/${subscriberId}`)
      .then(setPreview)
      .catch((e) => toast('error', errorMessage(e)))
      .finally(() => setLoading(false));
  }, [subscriberId, toast]);

  const sendTest = async () => {
    if (!preview) return;
    setSending(true);
    try {
      const r = await api.post<{ ok: boolean; message: string }>(
        `/runs/${preview.run_id}/retry-email`,
      );
      toast('success', r.message || '测试邮件已发送');
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal title="周报预览" sub={`SUBSCRIBER ${subscriberId}`} onClose={onClose} wide>
      {loading ? (
        <div className="flex h-48 items-center justify-center gap-3 text-mute">
          <Spinner /> 正在生成周报预览…
        </div>
      ) : preview ? (
        <div>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="font-mono text-[11px] tracking-[0.08em] text-mute">
              主题：{preview.subject}
            </div>
            <Button variant="primary" loading={sending} onClick={sendTest}>
              发送测试邮件
            </Button>
          </div>
          <iframe
            title="digest-preview"
            srcDoc={preview.html}
            sandbox=""
            className="h-[60vh] w-full border border-hair bg-white"
          />
          <p className="mt-2 font-mono text-[10px] tracking-[0.12em] text-faint">
            RUN ID {preview.run_id} · 测试邮件将重新发送该期周报
          </p>
        </div>
      ) : (
        <div className="py-10 text-center font-mono text-[11px] tracking-[0.2em] text-faint">
          无法生成预览
        </div>
      )}
    </Modal>
  );
}

function runStatusBadge(status: string) {
  const s = status.toLowerCase();
  if (s.includes('success') || s === 'done' || s === 'completed')
    return <Badge tone="success">成功</Badge>;
  if (s.includes('fail') || s === 'error') return <Badge tone="danger">失败</Badge>;
  if (s.includes('run') || s.includes('pending')) return <Badge tone="info">运行中</Badge>;
  return <Badge>{status}</Badge>;
}

function emailStatusBadge(status: string) {
  const s = (status || '').toLowerCase();
  if (s.includes('sent') || s.includes('success')) return <Badge tone="success">已发送</Badge>;
  if (s.includes('fail')) return <Badge tone="danger">失败</Badge>;
  if (s.includes('skip') || s.includes('disable')) return <Badge>未启用</Badge>;
  return <Badge>{status || '—'}</Badge>;
}

export default function SchedulePage() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [cfg, setCfg] = useState<ScheduleConfig>({
    enabled: false,
    day_of_week: 0,
    hour: 8,
    minute: 0,
    timezone: 'Asia/Shanghai',
  });

  const [subscribers, setSubscribers] = useState<Subscriber[]>([]);
  const [selectedSubs, setSelectedSubs] = useState<number[]>([]);
  const [sendEmail, setSendEmail] = useState(true);
  const [force, setForce] = useState(false);
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState<JobStatus | null>(null);

  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [previewSubId, setPreviewSubId] = useState<number | null>(null);

  const loadConfig = useCallback(async () => {
    try {
      const c = await api.get<ScheduleConfig>('/config/schedule');
      setCfg(c);
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const loadRuns = useCallback(async () => {
    setRunsLoading(true);
    try {
      const data = await api.get<RunInfo[]>('/runs', { limit: 20 });
      setRuns(Array.isArray(data) ? data : []);
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setRunsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void loadConfig();
    void loadRuns();
    api
      .get<Subscriber[]>('/subscribers')
      .then((d) => setSubscribers(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, [loadConfig, loadRuns]);

  const saveConfig = async () => {
    setSaving(true);
    try {
      await api.put('/config/schedule', {
        enabled: cfg.enabled,
        day_of_week: Number(cfg.day_of_week),
        hour: Number(cfg.hour),
        minute: Number(cfg.minute),
        timezone: cfg.timezone,
      });
      toast('success', '定时任务配置已保存');
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const pollJob = useCallback(
    async (jobId: string) => {
      try {
        const j = await api.get<JobStatus>(`/pipeline/jobs/${jobId}`);
        setJob(j);
        if (j.status === 'done' || j.status === 'failed' || j.status === 'error') {
          setRunning(false);
          toast(j.status === 'done' ? 'success' : 'error', j.message || `任务${j.status}`);
          void loadRuns();
        }
      } catch (e) {
        setRunning(false);
        toast('error', errorMessage(e));
      }
    },
    [loadRuns, toast],
  );

  usePolling(running && !!job, 2000, () => {
    if (job) void pollJob(job.job_id);
  });

  const manualRun = async () => {
    setRunning(true);
    setJob(null);
    try {
      const r = await api.post<{ job_id: string }>('/pipeline/run', {
        subscriber_ids: selectedSubs.length > 0 ? selectedSubs : undefined,
        send_email: sendEmail,
        force,
      });
      toast('info', '任务已启动，正在执行…');
      await pollJob(r.job_id);
    } catch (e) {
      setRunning(false);
      toast('error', errorMessage(e));
    }
  };

  const retryEmail = async (run: RunInfo) => {
    setRetryingId(run.id);
    try {
      const r = await api.post<{ ok: boolean; message: string }>(`/runs/${run.id}/retry-email`);
      toast('success', r.message || '邮件已重新发送');
      void loadRuns();
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setRetryingId(null);
    }
  };

  const toggleSub = (id: number) => {
    setSelectedSubs((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const progress = Math.max(0, Math.min(100, job?.progress ?? 0));

  return (
    <div>
      <PageHeader title="定时任务" desc="配置每周自动发送时间，或手动触发论文检索与周报发送" />

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 定时配置 */}
        <Card title="每周定时发送">
          {loading ? (
            <div className="flex h-32 items-center justify-center gap-3 text-mute">
              <Spinner /> 加载中…
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <Toggle
                checked={cfg.enabled}
                onChange={(v) => setCfg({ ...cfg, enabled: v })}
                label="启用每周自动执行"
              />
              <div className="grid grid-cols-3 gap-3">
                <Field label="星期">
                  <Select
                    value={cfg.day_of_week}
                    onChange={(e) => setCfg({ ...cfg, day_of_week: Number(e.target.value) })}
                  >
                    {DAY_OPTIONS.map((d) => (
                      <option key={d.value} value={d.value}>
                        {d.label}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="小时">
                  <Input
                    type="number"
                    min={0}
                    max={23}
                    value={cfg.hour}
                    onChange={(e) => setCfg({ ...cfg, hour: Number(e.target.value) })}
                  />
                </Field>
                <Field label="分钟">
                  <Input
                    type="number"
                    min={0}
                    max={59}
                    value={cfg.minute}
                    onChange={(e) => setCfg({ ...cfg, minute: Number(e.target.value) })}
                  />
                </Field>
              </div>
              <div className="font-mono text-[11px] tracking-[0.12em] text-faint">
                时区：{cfg.timezone || '—'}
              </div>
              <div>
                <Button variant="primary" loading={saving} onClick={saveConfig}>
                  保存配置
                </Button>
              </div>
            </div>
          )}
        </Card>

        {/* 手动执行 */}
        <Card title="手动执行" extra={running ? <Badge tone="info">执行中</Badge> : undefined}>
          <div className="flex flex-col gap-4">
            <Field label="选择订阅用户" hint="不选则对所有启用中的用户执行">
              <div className="max-h-[132px] overflow-y-auto border border-hair p-2">
                {subscribers.length === 0 && (
                  <div className="px-2 py-1 font-mono text-[11px] text-faint">暂无订阅用户</div>
                )}
                {subscribers.map((s) => (
                  <label key={s.id} className="flex cursor-pointer items-center gap-2.5 px-2 py-1.5 text-[13px] text-mute hover:text-ink">
                    <input
                      type="checkbox"
                      checked={selectedSubs.includes(s.id)}
                      onChange={() => toggleSub(s.id)}
                      className="h-3.5 w-3.5 accent-[#53e6a6]"
                    />
                    <span className="truncate">
                      {s.name} <span className="font-mono text-[11px] text-faint">{s.email}</span>
                    </span>
                    {!s.enabled && <Badge>暂停</Badge>}
                  </label>
                ))}
              </div>
            </Field>
            <div className="flex flex-wrap gap-5">
              <Toggle checked={sendEmail} onChange={setSendEmail} label="发送邮件" />
              <Toggle checked={force} onChange={setForce} label="强制重新运行（忽略本周已发送）" />
            </div>

            {job && (
              <div className="border border-hair bg-[rgba(150,160,190,.04)] px-4 py-3">
                <div className="mb-2 flex items-center justify-between font-mono text-[11px] tracking-[0.12em]">
                  <span className="text-mute">{job.message || '执行中…'}</span>
                  <span className="text-ink">{progress}%</span>
                </div>
                <div className="h-1.5 w-full bg-[rgba(150,160,190,.14)]">
                  <div
                    className="h-full transition-all duration-500"
                    style={{
                      width: `${progress}%`,
                      background:
                        job.status === 'failed' || job.status === 'error' ? '#ff9d94' : '#53e6a6',
                    }}
                  />
                </div>
              </div>
            )}

            <div>
              <Button variant="primary" loading={running} onClick={manualRun}>
                {running ? '执行中…' : '开始执行'}
              </Button>
            </div>
          </div>
        </Card>
      </div>

      {/* 周报预览入口 */}
      <Card title="周报预览" className="mt-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[13px] text-mute">选择订阅用户，预览其个性化周报 HTML（预览弹窗内可发送测试邮件）：</span>
          <Select
            value=""
            onChange={(e) => {
              if (e.target.value) setPreviewSubId(Number(e.target.value));
            }}
            className="w-auto! min-w-[260px]"
          >
            <option value="">选择用户…</option>
            {subscribers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}（{s.email}）
              </option>
            ))}
          </Select>
        </div>
      </Card>

      {/* 运行记录 */}
      <Card title="任务运行记录" className="mt-4">
        {runsLoading ? (
          <div className="flex h-24 items-center justify-center gap-3 text-mute">
            <Spinner /> 加载中…
          </div>
        ) : runs.length === 0 ? (
          <div className="py-6 text-center font-mono text-[11px] tracking-[0.2em] text-faint">
            暂无运行记录
          </div>
        ) : (
          <TableShell head={['开始时间', '订阅用户', '状态', '检索 / 推荐', '邮件状态', '操作']}>
            {runs.map((r) => (
              <tr key={r.id} className="border-b border-[rgba(150,160,190,.08)] last:border-0">
                <td className="whitespace-nowrap px-4 py-3 font-mono text-[12px] text-mute">
                  {fmtDateTime(r.started_at)}
                </td>
                <td className="px-4 py-3 text-ink">{r.subscriber_name}</td>
                <td className="px-4 py-3">{runStatusBadge(r.status)}</td>
                <td className="whitespace-nowrap px-4 py-3 font-mono text-[12px] text-mute">
                  {r.papers_found} / {r.papers_selected}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {emailStatusBadge(r.email_status)}
                    {r.email_error && (
                      <span className="max-w-[200px] truncate text-[11px] text-danger" title={r.email_error}>
                        {r.email_error}
                      </span>
                    )}
                  </div>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <Button
                    variant="ghost"
                    className="px-2"
                    loading={retryingId === r.id}
                    onClick={() => retryEmail(r)}
                    title="重新发送该期周报邮件"
                  >
                    重试邮件
                  </Button>
                </td>
              </tr>
            ))}
          </TableShell>
        )}
      </Card>

      {previewSubId !== null && (
        <DigestPreviewModal subscriberId={previewSubId} onClose={() => setPreviewSubId(null)} />
      )}
    </div>
  );
}
