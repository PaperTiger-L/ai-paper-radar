import { useCallback, useEffect, useState } from 'react';
import { api, errorMessage } from '../api';
import type { Subscriber } from '../types';
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
  keywords: string; // 逗号分隔
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
  keywords: '',
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
    keywords: (s.keywords ?? []).join(', '),
    venues: [...(s.venues ?? [])],
    customVenue: '',
    papers_per_week: s.papers_per_week ?? 8,
    enabled: s.enabled,
  };
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
      keywords: form.keywords
        .split(/[,，\n]/)
        .map((s) => s.trim())
        .filter(Boolean),
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
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="接收邮箱" required>
          <Input
            type="email"
            value={form.email}
            onChange={(e) => set('email', e.target.value)}
            placeholder="name@example.com"
          />
        </Field>
        <Field label="研究领域" required>
          <Input
            value={form.field}
            onChange={(e) => set('field', e.target.value)}
            placeholder="如：大语言模型、计算机视觉"
          />
        </Field>
        <div className="md:col-span-2">
          <Field label="研究方法" hint="如：强化学习、RAG、Agent、深度学习">
            <Textarea
              value={form.methods}
              onChange={(e) => set('methods', e.target.value)}
              placeholder="例如：强化学习、检索增强生成、多智能体协作"
            />
          </Field>
        </div>
        <div className="md:col-span-2 border-t border-hair pt-4">
          <div className="mb-3 font-mono text-[10px] tracking-[0.24em] text-faint">订阅推送计划</div>
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
        <TableShell head={['接收邮箱', '研究领域', '每周推荐', '推送状态', '操作']}>
          {list.map((s) => (
            <tr key={s.id} className="border-b border-[rgba(150,160,190,.08)] last:border-0 hover:bg-[rgba(150,160,190,.03)]">
              <td className="px-4 py-3 font-mono text-[12px] text-ink">{s.email}</td>
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
              <td colSpan={5} className="px-4 py-10 text-center font-mono text-[11px] tracking-[0.2em] text-faint">
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
          message={`确定删除订阅用户 ${deleting.email} 吗？该用户将不再收到论文周报，此操作不可恢复。`}
          onConfirm={confirmDelete}
          onClose={() => setDeleting(null)}
          loading={deletingLoading}
        />
      )}
    </div>
  );
}
