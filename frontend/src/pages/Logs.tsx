import { useCallback, useEffect, useState } from 'react';
import { api, errorMessage } from '../api';
import type { LogItem, PageResult } from '../types';
import {
  Badge,
  Button,
  ConfirmModal,
  Input,
  PageHeader,
  Pagination,
  Select,
  Spinner,
  TableShell,
  fmtDateTime,
  useToast,
} from '../ui';

const PAGE_SIZE = 20;
const CATEGORIES = [
  { value: '', label: '全部分类' },
  { value: 'search', label: 'search · 论文搜索' },
  { value: 'llm', label: 'llm · LLM 调用' },
  { value: 'pipeline', label: 'pipeline · 任务执行' },
  { value: 'email', label: 'email · 邮件发送' },
  { value: 'scheduler', label: 'scheduler · 定时任务' },
  { value: 'auth', label: 'auth · 登录鉴权' },
  { value: 'system', label: 'system · 系统' },
];
const LEVELS = [
  { value: '', label: '全部级别' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
];

function levelBadge(level: string) {
  const l = level.toUpperCase();
  if (l === 'ERROR') return <Badge tone="danger">ERROR</Badge>;
  if (l === 'WARNING') return <Badge tone="warn">WARNING</Badge>;
  return <Badge tone="success">INFO</Badge>;
}

export default function Logs() {
  const toast = useToast();
  const [items, setItems] = useState<LogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const [fCategory, setFCategory] = useState('');
  const [fLevel, setFLevel] = useState('');
  const [qInput, setQInput] = useState('');
  const [q, setQ] = useState('');

  const [showClean, setShowClean] = useState(false);
  const [cleaning, setCleaning] = useState(false);

  const load = useCallback(
    async (p: number, cat: string, lv: string, kw: string) => {
      setLoading(true);
      try {
        const data = await api.get<PageResult<LogItem>>('/logs', {
          category: cat || undefined,
          level: lv || undefined,
          q: kw || undefined,
          page: p,
          page_size: PAGE_SIZE,
        });
        setItems(data.items ?? []);
        setTotal(data.total ?? 0);
      } catch (e) {
        toast('error', errorMessage(e));
      } finally {
        setLoading(false);
      }
    },
    [toast],
  );

  useEffect(() => {
    void load(page, fCategory, fLevel, q);
  }, [load, page, fCategory, fLevel, q]);

  const applySearch = () => {
    setPage(1);
    setQ(qInput.trim());
  };

  const cleanLogs = async () => {
    setCleaning(true);
    try {
      await api.del('/logs', { days: 30 });
      toast('success', '已清理 30 天前的日志');
      setShowClean(false);
      setPage(1);
      void load(1, fCategory, fLevel, q);
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setCleaning(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="日志管理"
        desc="按时间倒序查看论文搜索、LLM 调用、任务与邮件发送日志"
        actions={
          <Button variant="danger" onClick={() => setShowClean(true)}>
            清理 30 天前日志
          </Button>
        }
      />

      <div className="mb-4 grid gap-3 md:grid-cols-[200px_160px_1fr_auto]">
        <Select value={fCategory} onChange={(e) => { setFCategory(e.target.value); setPage(1); }}>
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </Select>
        <Select value={fLevel} onChange={(e) => { setFLevel(e.target.value); setPage(1); }}>
          {LEVELS.map((l) => (
            <option key={l.value} value={l.value}>{l.label}</option>
          ))}
        </Select>
        <Input
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && applySearch()}
          placeholder="按日志内容搜索…"
        />
        <Button onClick={applySearch}>搜索</Button>
      </div>

      {loading ? (
        <div className="flex h-48 items-center justify-center gap-3 text-mute">
          <Spinner /> 加载中…
        </div>
      ) : (
        <>
          <TableShell head={['时间', '分类', '级别', '内容']}>
            {items.map((l) => (
              <tr key={l.id} className="border-b border-[rgba(150,160,190,.08)] align-top last:border-0">
                <td className="whitespace-nowrap px-4 py-3 font-mono text-[12px] text-mute">
                  {fmtDateTime(l.ts)}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <Badge>{l.category}</Badge>
                </td>
                <td className="whitespace-nowrap px-4 py-3">{levelBadge(l.level)}</td>
                <td className="max-w-[640px] break-words px-4 py-3 font-mono text-[12px] leading-relaxed text-ink">
                  {l.message}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center font-mono text-[11px] tracking-[0.2em] text-faint">
                  暂无日志
                </td>
              </tr>
            )}
          </TableShell>
          <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
        </>
      )}

      {showClean && (
        <ConfirmModal
          title="清理旧日志"
          message="确定删除 30 天前的所有日志吗？此操作不可恢复。"
          confirmText="确认清理"
          onConfirm={cleanLogs}
          onClose={() => setShowClean(false)}
          loading={cleaning}
        />
      )}
    </div>
  );
}
