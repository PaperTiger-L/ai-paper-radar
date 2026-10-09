import { useCallback, useEffect, useState } from 'react';
import { api, errorMessage } from '../api';
import type { DigestPreview, PageResult, Paper, Subscriber } from '../types';
import {
  Badge,
  Button,
  EmptyState,
  Field,
  Input,
  Modal,
  PageHeader,
  Pagination,
  Select,
  Spinner,
  TableShell,
  fmtDate,
  useToast,
} from '../ui';

const PAGE_SIZE = 15;
const SOURCES = [
  { value: '', label: '全部来源' },
  { value: 'openalex', label: 'OpenAlex' },
  { value: 'semantic_scholar', label: 'Semantic Scholar' },
  { value: 'arxiv', label: 'arXiv' },
  { value: 'crossref', label: 'Crossref' },
  { value: 'dblp', label: 'DBLP' },
];

function PaperDetail({ paper, onClose }: { paper: Paper; onClose: () => void }) {
  return (
    <Modal title="论文详情" sub={`ID ${paper.id}`} onClose={onClose} wide>
      <div className="flex flex-col gap-5">
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            {paper.is_preprint && <Badge tone="warn">预印本</Badge>}
            {!paper.is_preprint && paper.venue && <Badge tone="info">{paper.venue}</Badge>}
            {typeof paper.relevance_score === 'number' && (
              <Badge tone="success">相关度 {paper.relevance_score.toFixed(2)}</Badge>
            )}
          </div>
          <h3 className="text-[17px] font-medium leading-relaxed text-ink">{paper.title}</h3>
          {paper.zh_title && (
            <p className="mt-1.5 text-[14px] leading-relaxed text-mute">{paper.zh_title}</p>
          )}
          <p className="mt-2 font-mono text-[11px] leading-relaxed text-faint">
            {(paper.authors ?? []).join(', ')}
          </p>
          <p className="mt-1 font-mono text-[11px] text-faint">
            {paper.venue || '—'} · {fmtDate(paper.published_date)} · 来源 {paper.source || '—'}
            {paper.subscriber_name ? ` · 推荐给 ${paper.subscriber_name}` : ''}
          </p>
          {paper.url && (
            <a
              href={paper.url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block font-mono text-[11px] tracking-[0.08em] text-info underline underline-offset-4 hover:text-ink"
            >
              查看原文 →
            </a>
          )}
        </div>

        {paper.zh_abstract && (
          <section>
            <h4 className="mb-1.5 font-mono text-[10px] tracking-[0.24em] text-faint">中文摘要</h4>
            <p className="text-[13px] leading-relaxed text-mute">{paper.zh_abstract}</p>
          </section>
        )}
        {paper.abstract && (
          <section>
            <h4 className="mb-1.5 font-mono text-[10px] tracking-[0.24em] text-faint">ABSTRACT</h4>
            <p className="text-[13px] leading-relaxed text-mute">{paper.abstract}</p>
          </section>
        )}
        {(paper.innovations ?? []).length > 0 && (
          <section>
            <h4 className="mb-1.5 font-mono text-[10px] tracking-[0.24em] text-faint">核心创新点</h4>
            <ul className="list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-mute">
              {paper.innovations.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </section>
        )}
        {paper.recommend_reason && (
          <section className="border border-[rgba(83,230,166,.25)] bg-[rgba(83,230,166,.05)] px-4 py-3">
            <h4 className="mb-1.5 font-mono text-[10px] tracking-[0.24em] text-success">推荐理由</h4>
            <p className="text-[13px] leading-relaxed text-ink">{paper.recommend_reason}</p>
          </section>
        )}
      </div>
    </Modal>
  );
}

function DigestPreviewModal({
  subscriber,
  onClose,
}: {
  subscriber: Subscriber;
  onClose: () => void;
}) {
  const toast = useToast();
  const [preview, setPreview] = useState<DigestPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    api
      .get<DigestPreview>(`/digest/preview/${subscriber.id}`)
      .then(setPreview)
      .catch((e) => toast('error', errorMessage(e)))
      .finally(() => setLoading(false));
  }, [subscriber.id, toast]);

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
    <Modal
      title="周报预览"
      sub={`收件人 ${subscriber.name} · ${subscriber.email}`}
      onClose={onClose}
      wide
    >
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
        <EmptyState text="无法生成预览，请稍后重试" />
      )}
    </Modal>
  );
}

export default function Papers() {
  const toast = useToast();
  const [subscribers, setSubscribers] = useState<Subscriber[]>([]);
  const [items, setItems] = useState<Paper[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const [fSubscriber, setFSubscriber] = useState('');
  const [fSource, setFSource] = useState('');
  const [q, setQ] = useState('');
  const [qInput, setQInput] = useState('');

  const [detail, setDetail] = useState<Paper | null>(null);
  const [previewSub, setPreviewSub] = useState<Subscriber | null>(null);

  const load = useCallback(
    async (p: number, fs: string, fso: string, kw: string) => {
      setLoading(true);
      try {
        const data = await api.get<PageResult<Paper>>('/papers', {
          subscriber_id: fs || undefined,
          source: fso || undefined,
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
    api
      .get<Subscriber[]>('/subscribers')
      .then((d) => setSubscribers(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    void load(page, fSubscriber, fSource, q);
  }, [load, page, fSubscriber, fSource, q]);

  const applySearch = () => {
    setPage(1);
    setQ(qInput.trim());
  };

  return (
    <div>
      <PageHeader
        title="论文管理"
        desc="查看检索到的论文及 AI 分析结果，点击行查看详情"
        actions={
          <div className="flex items-center gap-2">
            <Select
              value={previewSub ? String(previewSub.id) : ''}
              onChange={(e) => {
                const s = subscribers.find((x) => String(x.id) === e.target.value);
                if (s) setPreviewSub(s);
              }}
              className="w-auto!"
            >
              <option value="">周报预览：选择用户…</option>
              {subscribers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}（{s.email}）
                </option>
              ))}
            </Select>
          </div>
        }
      />

      {/* 筛选栏 */}
      <div className="mb-4 grid gap-3 md:grid-cols-[220px_200px_1fr_auto]">
        <Select value={fSubscriber} onChange={(e) => { setFSubscriber(e.target.value); setPage(1); }}>
          <option value="">全部订阅用户</option>
          {subscribers.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
        <Select value={fSource} onChange={(e) => { setFSource(e.target.value); setPage(1); }}>
          {SOURCES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </Select>
        <Input
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && applySearch()}
          placeholder="按标题 / 关键词搜索…"
        />
        <Button onClick={applySearch}>搜索</Button>
      </div>

      {loading ? (
        <div className="flex h-48 items-center justify-center gap-3 text-mute">
          <Spinner /> 加载中…
        </div>
      ) : (
        <>
          <TableShell head={['标题', '会议 / 期刊', '类型', '日期', '相关度', '推荐给']}>
            {items.map((p) => (
              <tr
                key={p.id}
                onClick={() => setDetail(p)}
                className="cursor-pointer border-b border-[rgba(150,160,190,.08)] last:border-0 hover:bg-[rgba(150,160,190,.05)]"
              >
                <td className="max-w-[380px] px-4 py-3">
                  <div className="truncate text-ink" title={p.title}>
                    {p.title}
                  </div>
                  {p.zh_title && (
                    <div className="truncate text-[12px] text-faint" title={p.zh_title}>
                      {p.zh_title}
                    </div>
                  )}
                </td>
                <td className="max-w-[160px] truncate px-4 py-3 text-mute" title={p.venue}>
                  {p.venue || '—'}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  {p.is_preprint ? <Badge tone="warn">预印本</Badge> : <Badge tone="info">正式发表</Badge>}
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-mono text-[12px] text-mute">
                  {fmtDate(p.published_date)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-mono text-[12px] text-success">
                  {typeof p.relevance_score === 'number' ? p.relevance_score.toFixed(2) : '—'}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-mute">{p.subscriber_name || '—'}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center font-mono text-[11px] tracking-[0.2em] text-faint">
                  暂无论文数据
                </td>
              </tr>
            )}
          </TableShell>
          <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />
        </>
      )}

      {detail && <PaperDetail paper={detail} onClose={() => setDetail(null)} />}
      {previewSub && <DigestPreviewModal subscriber={previewSub} onClose={() => setPreviewSub(null)} />}
    </div>
  );
}

