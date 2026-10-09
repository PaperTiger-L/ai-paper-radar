import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, errorMessage } from '../api';
import type { DashboardData } from '../types';
import { Badge, Card, PageHeader, Spinner, fmtDateTime, useToast } from '../ui';

const DAY_NAMES = ['一', '二', '三', '四', '五', '六', '日'];

export function describeSchedule(d: DashboardData): string {
  if (!d.schedule_enabled) return '未启用';
  // next_run_at 由后端直接给出
  return d.next_run_at ? fmtDateTime(d.next_run_at) : '未启用';
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="border border-hair bg-panel px-5 py-4">
      <div className="font-mono text-[10px] tracking-[0.24em] text-faint">{label}</div>
      <div className="mt-2 text-[30px] font-light leading-none text-ink">{value}</div>
      {sub && <div className="mt-2 text-[12px] text-mute">{sub}</div>}
    </div>
  );
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center justify-between py-2.5">
      <span className="text-[13px] text-mute">{label}</span>
      <span className="inline-flex items-center gap-2">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{
            background: ok ? '#53e6a6' : '#5d6580',
            boxShadow: ok ? '0 0 8px rgba(83,230,166,.7)' : 'none',
          }}
        />
        <span className="font-mono text-[11px] tracking-[0.14em]" style={{ color: ok ? '#53e6a6' : '#5d6580' }}>
          {ok ? '已配置' : '未配置'}
        </span>
      </span>
    </div>
  );
}

function runStatusBadge(status: string) {
  const s = status.toLowerCase();
  if (s.includes('success') || s === 'done' || s === 'completed')
    return <Badge tone="success">成功</Badge>;
  if (s.includes('fail') || s === 'error') return <Badge tone="danger">失败</Badge>;
  if (s.includes('run')) return <Badge tone="info">运行中</Badge>;
  return <Badge>{status}</Badge>;
}

function emailStatusBadge(status: string) {
  const s = status.toLowerCase();
  if (s.includes('sent') || s.includes('success')) return <Badge tone="success">已发送</Badge>;
  if (s.includes('fail')) return <Badge tone="danger">失败</Badge>;
  if (s.includes('skip')) return <Badge>未启用</Badge>;
  return <Badge>{status || '—'}</Badge>;
}

export default function Dashboard() {
  const toast = useToast();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<DashboardData>('/dashboard')
      .then(setData)
      .catch((e) => toast('error', errorMessage(e)))
      .finally(() => setLoading(false));
  }, [toast]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center gap-3 text-mute">
        <Spinner /> 加载中…
      </div>
    );
  }
  if (!data) {
    return (
      <PageHeader
        title="总览"
        actions={
          <button
            className="border border-hair px-4 py-2 font-mono text-[11px] tracking-[0.18em] text-mute hover:text-ink"
            onClick={() => window.location.reload()}
          >
            重试
          </button>
        }
      />
    );
  }

  return (
    <div>
      <PageHeader title="总览" desc="订阅、论文与任务运行的整体状态" />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="订阅用户" value={data.subscriber_count} sub={`启用中 ${data.active_subscriber_count}`} />
        <StatCard label="近 7 天检索论文" value={data.papers_7d} />
        <StatCard label="近 7 天推荐论文" value={data.recommendations_7d} />
        <StatCard
          label="定时任务"
          value={data.schedule_enabled ? '已启用' : '未启用'}
          sub={data.schedule_enabled ? `下次运行 ${describeSchedule(data)}` : undefined}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card
          title="系统状态"
          extra={
            <Link to="/llm" className="font-mono text-[10px] tracking-[0.2em] text-faint hover:text-ink">
              配置 →
            </Link>
          }
        >
          <div className="divide-y divide-[rgba(150,160,190,.08)]">
            <StatusDot ok={data.llm_configured} label="LLM 模型" />
            <StatusDot ok={data.smtp_configured} label="SMTP 邮件" />
            <StatusDot ok={data.schedule_enabled} label="定时任务" />
          </div>
        </Card>

        <Card
          title="最近一次运行"
          extra={
            <Link to="/schedule" className="font-mono text-[10px] tracking-[0.2em] text-faint hover:text-ink">
              详情 →
            </Link>
          }
        >
          {data.last_run ? (
            <div className="text-[13px] leading-loose">
              <div className="flex items-center justify-between">
                <span className="text-mute">{data.last_run.subscriber_name}</span>
                {runStatusBadge(data.last_run.status)}
              </div>
              <div className="text-mute">
                检索 {data.last_run.papers_found} 篇 · 推荐 {data.last_run.papers_selected} 篇
              </div>
              <div className="font-mono text-[11px] text-faint">
                {fmtDateTime(data.last_run.started_at)}
              </div>
            </div>
          ) : (
            <div className="py-4 font-mono text-[11px] tracking-[0.2em] text-faint">尚无运行记录</div>
          )}
        </Card>

        <Card title="下次运行">
          <div className="py-2">
            <div className="text-[22px] font-light text-ink">
              {data.next_run_at ? fmtDateTime(data.next_run_at) : '—'}
            </div>
            <div className="mt-2 font-mono text-[10px] tracking-[0.2em] text-faint">
              {data.schedule_enabled ? '按定时计划自动执行' : '定时任务未启用'}
            </div>
          </div>
        </Card>
      </div>

      <Card title="最近任务运行" className="mt-4">
        {data.recent_runs.length === 0 ? (
          <div className="py-4 font-mono text-[11px] tracking-[0.2em] text-faint">暂无记录</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-[13px]">
              <thead>
                <tr className="border-b border-hair">
                  {['订阅用户', '开始时间', '状态', '检索 / 推荐', '邮件状态'].map((h) => (
                    <th key={h} className="px-3 py-2 font-mono text-[10px] font-normal tracking-[0.2em] text-faint">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.recent_runs.slice(0, 5).map((r) => (
                  <tr key={r.id} className="border-b border-[rgba(150,160,190,.08)] last:border-0">
                    <td className="px-3 py-2.5 text-ink">{r.subscriber_name}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 font-mono text-[12px] text-mute">
                      {fmtDateTime(r.started_at)}
                    </td>
                    <td className="px-3 py-2.5">{runStatusBadge(r.status)}</td>
                    <td className="px-3 py-2.5 font-mono text-[12px] text-mute">
                      {r.papers_found} / {r.papers_selected}
                    </td>
                    <td className="px-3 py-2.5">{emailStatusBadge(r.email_status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

export { DAY_NAMES };
