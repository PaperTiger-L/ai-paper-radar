import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, errorMessage } from '../api';
import type { Discipline, Subscriber, VenueLibrary } from '../types';
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
  disciplines: string[];
  research_direction: string;
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
  disciplines: [],
  research_direction: '',
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
    disciplines: [...(s.disciplines ?? [])],
    research_direction: s.research_direction ?? '',
    research_problem: s.research_problem,
    methods: s.methods ?? '',
    keywords: [...(s.keywords ?? [])],
    venues: [...(s.venues ?? [])],
    customVenue: '',
    papers_per_week: s.papers_per_week ?? 8,
    enabled: s.enabled,
  };
}

/** 刊会库中全部刊会名集合（用于区分用户自定义项） */
function libraryVenueNames(lib: VenueLibrary | null): Set<string> {
  const s = new Set<string>();
  for (const d of lib?.disciplines ?? []) for (const v of d.venues) s.add(v.name);
  return s;
}

/** 所选学科的全部刊会名（去重保序） */
function unionVenues(lib: VenueLibrary | null, disciplineIds: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const map = new Map((lib?.disciplines ?? []).map((d) => [d.id, d]));
  for (const id of disciplineIds) {
    for (const v of map.get(id)?.venues ?? []) {
      if (!seen.has(v.name)) {
        seen.add(v.name);
        out.push(v.name);
      }
    }
  }
  return out;
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

/** 学科多选：按门类分组展示 */
function DisciplinePicker({
  library,
  value,
  onToggle,
}: {
  library: VenueLibrary | null;
  value: string[];
  onToggle: (id: string) => void;
}) {
  const groups = useMemo(() => {
    const m = new Map<string, Discipline[]>();
    for (const d of library?.disciplines ?? []) {
      const g = m.get(d.category) ?? [];
      g.push(d);
      m.set(d.category, g);
    }
    return [...m.entries()];
  }, [library]);

  const toggle = useCallback(
    (id: string) => onToggle(id),
    [onToggle],
  );

  if (!library) return <div className="font-mono text-[12px] text-faint">刊会库加载中…</div>;

  return (
    <div className="space-y-3">
      {groups.map(([cat, items]) => (
        <div key={cat}>
          <div className="mb-1.5 font-mono text-[10px] tracking-[0.2em] text-faint">{cat}</div>
          <div className="flex flex-wrap gap-2">
            {items.map((d) => {
              const on = value.includes(d.id);
              return (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => toggle(d.id)}
                  className={`border px-2.5 py-1 text-[12px] transition-colors ${
                    on
                      ? 'border-[rgba(83,230,166,.55)] bg-[rgba(83,230,166,.12)] text-ink'
                      : 'border-hair bg-[rgba(150,160,190,.04)] text-mute hover:border-hair-2 hover:text-ink'
                  }`}
                >
                  {d.name}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      {value.length > 0 && (
        <div className="font-mono text-[11px] text-faint">已选 {value.length} 个学科</div>
      )}
    </div>
  );
}

/** 刊会选择：展示所选学科的刊/会（默认全选），支持手动取消与自定义添加 */
function VenuePicker({
  library,
  disciplineIds,
  value,
  onChange,
  customVenue,
  onCustomVenue,
}: {
  library: VenueLibrary | null;
  disciplineIds: string[];
  value: string[];
  onChange: (v: string[]) => void;
  customVenue: string;
  onCustomVenue: (v: string) => void;
}) {
  const toggle = (v: string) => {
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  };

  const addCustom = () => {
    const v = customVenue.trim();
    if (!v) return;
    if (!value.includes(v)) onChange([...value, v]);
    onCustomVenue('');
  };

  const libNames = useMemo(() => libraryVenueNames(library), [library]);
  const groups = useMemo(() => {
    const map = new Map((library?.disciplines ?? []).map((d) => [d.id, d]));
    return disciplineIds
      .map((id) => map.get(id))
      .filter((d): d is Discipline => !!d);
  }, [library, disciplineIds]);

  // 预设中没有、但已选的自定义项单独展示
  const customs = value.filter((v) => !libNames.has(v));

  const renderGroup = (title: string, items: { name: string; type: string }[]) => {
    const allOn = items.length > 0 && items.every((v) => value.includes(v.name));
    return (
      <div className="mb-3">
        <div className="mb-1.5 flex items-center justify-between">
          <div className="font-mono text-[10px] tracking-[0.2em] text-faint">{title}</div>
          {items.length > 1 && (
            <button
              type="button"
              className="font-mono text-[10px] text-mute hover:text-ink"
              onClick={() => {
                const names = items.map((v) => v.name);
                onChange(
                  allOn
                    ? value.filter((x) => !names.includes(x))
                    : [...value, ...names.filter((n) => !value.includes(n))],
                );
              }}
            >
              {allOn ? '清空' : '全选'}
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {items.map((v) => {
            const on = value.includes(v.name);
            return (
              <button
                key={v.name}
                type="button"
                onClick={() => toggle(v.name)}
                title={v.type === 'preprint' ? '预印本' : v.type === 'conference' ? '会议' : '期刊'}
                className={`border px-2.5 py-1 text-[12px] transition-colors ${
                  on
                    ? 'border-[rgba(83,230,166,.55)] bg-[rgba(83,230,166,.12)] text-ink'
                    : 'border-hair bg-[rgba(150,160,190,.04)] text-mute hover:border-hair-2 hover:text-ink'
                }`}
              >
                {v.name}
                {v.type === 'preprint' && <span className="ml-1 text-[10px] text-faint">预印本</span>}
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  if (disciplineIds.length === 0) {
    return (
      <div className="font-mono text-[12px] text-faint">
        请先在上方选择学科，这里会列出对应学科的期刊 / 顶会（默认全选）。
      </div>
    );
  }

  return (
    <div>
      {groups.map((d) => renderGroup(d.name, d.venues))}
      {customs.length > 0 && renderGroup('自定义', customs.map((name) => ({ name, type: 'custom' })))}
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
        <div className="mt-2 font-mono text-[11px] text-faint">
          已选 {value.length} 个刊会（硬过滤：周报只收录所选刊会范围内的论文）
        </div>
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
  const [library, setLibrary] = useState<VenueLibrary | null>(null);

  useEffect(() => {
    api
      .get<VenueLibrary>('/config/venues')
      .then(setLibrary)
      .catch(() => {});
  }, []);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  /** 学科切换：新增学科的刊会自动全选；移除学科的刊会同步移除；手动取消的保持不变 */
  const toggleDiscipline = (id: string) => {
    const has = form.disciplines.includes(id);
    const next = has ? form.disciplines.filter((x) => x !== id) : [...form.disciplines, id];
    const libNames = libraryVenueNames(library);
    if (has) {
      // 只移除"不再属于任何已选学科"的刊会；自定义项始终保留
      const remaining = new Set(unionVenues(library, next));
      setForm((f) => ({
        ...f,
        disciplines: next,
        venues: f.venues.filter((v) => remaining.has(v) || !libNames.has(v)),
      }));
    } else {
      const added = unionVenues(library, [id]).filter((v) => !form.venues.includes(v));
      setForm((f) => ({ ...f, disciplines: next, venues: [...f.venues, ...added] }));
    }
  };

  const submit = async () => {
    if (!form.email.trim() || form.disciplines.length === 0) {
      toast('error', '请填写接收邮箱并至少选择一个学科');
      return;
    }
    setSaving(true);
    const payload = {
      name: form.name.trim(),
      email: form.email.trim(),
      field: '',
      disciplines: form.disciplines,
      research_direction: form.research_direction.trim(),
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
      <div className="grid gap-4">
        <Field label="学科" required hint="多选，下方会自动列出对应学科的期刊 / 顶会">
          <DisciplinePicker library={library} value={form.disciplines} onToggle={toggleDiscipline} />
        </Field>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="研究方向" hint="一句话，如：大模型推理加速">
            <Input
              value={form.research_direction}
              onChange={(e) => set('research_direction', e.target.value)}
              placeholder="如：多智能体协作、环境催化材料"
            />
          </Field>
          <Field label="关键词" hint="回车添加，用于辅助搜索">
            <KeywordTags value={form.keywords} onChange={(v) => set('keywords', v)} />
          </Field>
        </div>
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
        <Field
          label="关注的会议 / 期刊"
          hint="根据所选学科自动列出，默认全选；周报只收录所选刊会范围内的论文"
        >
          <VenuePicker
            library={library}
            disciplineIds={form.disciplines}
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
  const [library, setLibrary] = useState<VenueLibrary | null>(null);

  useEffect(() => {
    api
      .get<VenueLibrary>('/config/venues')
      .then(setLibrary)
      .catch(() => {});
  }, []);

  const disciplineNameMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const d of library?.disciplines ?? []) m.set(d.id, d.name);
    return m;
  }, [library]);

  const disciplineNames = (s: Subscriber) =>
    (s.disciplines ?? []).map((id) => disciplineNameMap.get(id) ?? id).join('、') || s.field || '—';

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
        <TableShell head={['用户', '接收邮箱', '学科', '每周推荐', '推送状态', '操作']}>
          {list.map((s) => (
            <tr key={s.id} className="border-b border-[rgba(150,160,190,.08)] last:border-0 hover:bg-[rgba(150,160,190,.03)]">
              <td className="px-4 py-3 text-ink">{s.name}</td>
              <td className="px-4 py-3 font-mono text-[12px] text-mute">{s.email}</td>
              <td className="max-w-[220px] truncate px-4 py-3 text-mute" title={disciplineNames(s)}>
                {disciplineNames(s)}
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
