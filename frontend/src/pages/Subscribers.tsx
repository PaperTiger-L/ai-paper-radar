import { useCallback, useEffect, useState } from 'react';
import { api, errorMessage } from '../api';
import type { Subscriber, VenueLists } from '../types';
import {
  Badge,
  Button,
  ConfirmModal,
  Field,
  Input,
  Modal,
  PageHeader,
  Spinner,
  TableShell,
  Textarea,
  Toggle,
  useToast,
} from '../ui';

interface FormState {
  name: string;
  email: string;
  field: string;
  research_problem: string;
  methods: string;
  keywords: string[];
  venues: string[];
  customVenue: string;
  papers_per_week: number;
  enabled: boolean;
}

const emptyForm: FormState = {
  name: '',
  email: '',
  field: '',
  research_problem: '',
  methods: '',
  keywords: [],
  venues: [],
  customVenue: '',
  papers_per_week: 8,
  enabled: true,
};

function toForm(s?: Subscriber): FormState {
  if (!s) return { ...emptyForm };
  return {
    name: s.name,
    email: s.email,
    field: s.field,
    research_problem: s.research_problem,
    methods: s.methods ?? '',
    keywords: [...(s.keywords ?? [])],
    venues: [...(s.venues ?? [])],
    customVenue: '',
    papers_per_week: s.papers_per_week ?? 8,
    enabled: s.enabled,
  };
}

/** 关键词标签输入：回车/逗号添加，点击 × 删除 */
function KeywordTags({
  value,
  onChange,
}: {
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const [draft, setDraft] = useState('');

  const add = (raw: string) => {
    const v = raw.trim().replace(/[,，]+$/, '');
    if (v && !value.includes(v)) onChange([...value, v]);
  };

  const commitDraft = () => {
    if (draft.trim()) {
      add(draft);
      setDraft('');
    }
  };

  return (
    <div>
      {value.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {value.map((k) => (
            <span
              key={k}
              className="flex items-center gap-1.5 border border-hair-2 bg-[rgba(150,160,190,.08)] px-2.5 py-1 text-[12px] text-ink"
            >
              {k}
              <button
                type="button"
                onClick={() => onChange(value.filter((x) => x !== k))}
                className="text-faint transition-colors hover:text-danger"
                title="删除"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            commitDraft();
          }
        }}
        onBlur={commitDraft}
        placeholder="输入关键词后回车添加，如 LLM"
      />
    </div>
  );
}

function VenuePicker({
  value,
  onChange,
  customVenue,
  onCustomVenue,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  customVenue: string;
  onCustomVenue: (v: string) => void;
}) {
  const [lists, setLists] = useState<VenueLists | null>(null);

  useEffect(() => {
    api
      .get<VenueLists>('/venues')
      .then(setLists)
      .catch(() => {});
  }, []);

  const toggle = (v: string) => {
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  };

  const addCustom = () => {
    const v = customVenue.trim();
    if (!v) return;
    if (!value.includes(v)) onChange([...value, v]);
    onCustomVenue('');
  };

  const renderGroup = (title: string, items: string[]) => (
    <div className="mb-3">
      <div className="mb-1.5 font-mono text-[10px] tracking-[0.2em] text-faint">{title}</div>
      <div className="flex flex-wrap gap-2">
        {items.map((v) => {
          const on = value.includes(v);
          return (
            <button
              key={v}
              type="button"
              onClick={() => toggle(v)}
              className={`border px-2.5 py-1 text-[12px] transition-colors ${
                on
                  ? 'border-[rgba(83,230,166,.55)] bg-[rgba(83,230,166,.12)] text-ink'
                  : 'border-hair bg-[rgba(150,160,190,.04)] text-mute hover:border-hair-2 hover:text-ink'
              }`}
            >
              {v}
            </button>
          );
        })}
      </div>
    </div>
  );

  // 预设中没有、但用户已选的自定义项单独展示
  const preset = [...(lists?.conferences ?? []), ...(lists?.journals ?? [])];
  const customs = value.filter((v) => !preset.includes(v));

  return (
    <div>
      {renderGroup('顶级会议', lists?.conferences ?? [])}
      {renderGroup('顶级期刊', lists?.journals ?? [])}
      {customs.length > 0 && renderGroup('自定义', customs)}
      <div className="flex gap-2">
        <Input
          value={customVenue}
          onChange={(e) => onCustomVenue(e.target.value)}
          placeholder="输入自定义会议/期刊名称，回车添加"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addCustom();
            }
          }}
        />
        <Button type="button" onClick={addCustom}>
          添加
        </Button>
      </div>
      {value.length > 0 && (
        <div className="mt-2 font-mono text-[11px] text-faint">已选 {value.length} 个</div>
      )}
    </div>
  );
}

function SubscriberModal({
  editing,
  onClose,
  onSaved,
}: {
  editing: Subscriber | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<FormState>(() => toForm(editing ?? undefined));
  const [saving, setSaving] = useState(false);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.email.trim() || !form.field.trim()) {
      toast('error', '请填写接收邮箱和研究领域');
      return;
    }
    setSaving(true);
    const payload = {
      name: form.name.trim(),
      email: form.email.trim(),
      field: form.field.trim(),
      research_problem: form.research_problem.trim(),
      methods: form.methods.trim(),
      keywords: form.keywords,
      venues: form.venues,
      papers_per_week: Number(form.papers_per_week) || 8,
      enabled: form.enabled,
    };
    try {
      if (editing) {
        await api.put(`/subscribers/${editing.id}`, payload);
        toast('success', '用户信息已更新');
      } else {
        await api.post('/subscribers', payload);
        toast('success', '订阅用户已添加');
      }
      onSaved();
      onClose();
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={editing ? '编辑订阅用户' : '新增订阅用户'}
      sub={editing ? `ID ${editing.id}` : 'NEW SUBSCRIBER'}
      onClose={onClose}
      wide
    >
      {/* 基本信息 */}
      <div className="mb-3 font-mono text-[10px] tracking-[0.24em] text-faint">基本信息</div>
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="用户名称" hint="不填则用邮箱前缀">
          <Input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="如：张三" />
        </Field>
        <Field label="接收邮箱" required>
          <Input
            type="email"
            value={form.email}
            onChange={(e) => set('email', e.target.value)}
            placeholder="name@example.com"
          />
        </Field>
      </div>

      {/* 研究画像 */}
      <div className="mb-3 mt-6 font-mono text-[10px] tracking-[0.24em] text-faint">研究画像</div>
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="研究领域" required>
          <Input
            value={form.field}
            onChange={(e) => set('field', e.target.value)}
            placeholder="如：大语言模型、计算机视觉"
          />
        </Field>
        <Field label="关键词" hint="回车添加，用于辅助搜索">
          <KeywordTags value={form.keywords} onChange={(v) => set('keywords', v)} />
        </Field>
        <div className="md:col-span-2">
          <Field label="当前研究问题" hint="用自然语言描述重点关注的科研问题，系统据此理解研究需求">
            <Textarea
              value={form.research_problem}
              onChange={(e) => set('research_problem', e.target.value)}
              placeholder="例如：如何让多智能体系统在长程任务中保持稳定的协作与记忆…"
            />
          </Field>
        </div>
        <div className="md:col-span-2">
          <Field label="研究方法" hint="如：强化学习、RAG、Agent、深度学习">
            <Textarea
              value={form.methods}
              onChange={(e) => set('methods', e.target.value)}
              placeholder="例如：强化学习、检索增强生成、多智能体协作"
            />
          </Field>
        </div>
      </div>

      {/* 推送偏好 */}
      <div className="mb-3 mt-6 font-mono text-[10px] tracking-[0.24em] text-faint">推送偏好</div>
      <div className="grid gap-4">
        <Field label="关注的会议 / 期刊" hint="从预设中多选，也可自定义输入">
          <VenuePicker
            value={form.venues}
            onChange={(v) => set('venues', v)}
            customVenue={form.customVenue}
            onCustomVenue={(v) => set('customVenue', v)}
          />
        </Field>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="每周推荐论文数量" hint="1~50 篇">
            <Input
              type="number"
              min={1}
              max={50}
              value={form.papers_per_week}
              onChange={(e) => set('papers_per_week', Number(e.target.value))}
            />
          </Field>
          <div className="flex items-end pb-1">
            <Toggle checked={form.enabled} onChange={(v) => set('enabled', v)} label="启用邮件推送" />
          </div>
        </div>
      </div>
      <div className="mt-6 flex justify-end gap-3">
        <Button onClick={onClose}>取消</Button>
        <Button variant="primary" loading={saving} onClick={submit}>
          保存
        </Button>
      </div>
    </Modal>
  );
}

export default function Subscribers() {
  const toast = useToast();
  const [list, setList] = useState<Subscriber[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Subscriber | null>(null);
  const [deleting, setDeleting] = useState<Subscriber | null>(null);
  const [deletingLoading, setDeletingLoading] = useState(false);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<Subscriber[]>('/subscribers');
      setList(Array.isArray(data) ? data : []);
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleEnabled = async (s: Subscriber) => {
    setTogglingId(s.id);
    try {
      await api.put(`/subscribers/${s.id}`, { enabled: !s.enabled });
      setList((prev) => prev.map((x) => (x.id === s.id ? { ...x, enabled: !x.enabled } : x)));
      toast('success', !s.enabled ? '已启用推送' : '已暂停推送');
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setTogglingId(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    setDeletingLoading(true);
    try {
      await api.del(`/subscribers/${deleting.id}`);
      toast('success', '已删除');
      setDeleting(null);
      void load();
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setDeletingLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="用户管理"
        desc="管理论文周报的邮件订阅用户及其研究方向配置"
        actions={
          <Button
            variant="primary"
            onClick={() => {
              setEditing(null);
              setModalOpen(true);
            }}
          >
            + 新增用户
          </Button>
        }
      />

      {loading ? (
        <div className="flex h-48 items-center justify-center gap-3 text-mute">
          <Spinner /> 加载中…
        </div>
      ) : (
        <TableShell head={['用户', '接收邮箱', '研究领域', '每周推荐', '推送状态', '操作']}>
          {list.map((s) => (
            <tr key={s.id} className="border-b border-[rgba(150,160,190,.08)] last:border-0 hover:bg-[rgba(150,160,190,.03)]">
              <td className="px-4 py-3 text-ink">{s.name}</td>
              <td className="px-4 py-3 font-mono text-[12px] text-mute">{s.email}</td>
              <td className="max-w-[220px] truncate px-4 py-3 text-mute" title={s.field}>
                {s.field}
              </td>
              <td className="px-4 py-3 font-mono text-[12px] text-mute">{s.papers_per_week} 篇</td>
              <td className="px-4 py-3">
                <button
                  onClick={() => toggleEnabled(s)}
                  disabled={togglingId === s.id}
                  title="点击切换推送状态"
                  className="disabled:opacity-40"
                >
                  {s.enabled ? <Badge tone="success">启用中</Badge> : <Badge>已暂停</Badge>}
                </button>
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <Button
                  variant="ghost"
                  className="px-2"
                  onClick={() => {
                    setEditing(s);
                    setModalOpen(true);
                  }}
                >
                  编辑
                </Button>
                <Button variant="ghost" className="px-2 text-danger!" onClick={() => setDeleting(s)}>
                  删除
                </Button>
              </td>
            </tr>
          ))}
          {list.length === 0 && (
            <tr>
              <td colSpan={6} className="px-4 py-10 text-center font-mono text-[11px] tracking-[0.2em] text-faint">
                暂无订阅用户，点击右上角添加
              </td>
            </tr>
          )}
        </TableShell>
      )}

      {modalOpen && (
        <SubscriberModal
          editing={editing}
          onClose={() => setModalOpen(false)}
          onSaved={load}
        />
      )}
      {deleting && (
        <ConfirmModal
          title="删除订阅用户"
          message={`确定删除「${deleting.name}」（${deleting.email}）吗？该用户将不再收到论文周报，此操作不可恢复。`}
          onConfirm={confirmDelete}
          onClose={() => setDeleting(null)}
          loading={deletingLoading}
        />
      )}
    </div>
  );
}
