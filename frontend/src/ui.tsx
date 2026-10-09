import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';

/* ---------------- Toast ---------------- */

interface ToastItem {
  id: number;
  kind: 'success' | 'error' | 'info';
  text: string;
}

const ToastCtx = createContext<(kind: ToastItem['kind'], text: string) => void>(
  () => {},
);

export function useToast() {
  return useContext(ToastCtx);
}

let toastSeq = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((kind: ToastItem['kind'], text: string) => {
    const id = toastSeq++;
    setItems((prev) => [...prev.slice(-2), { id, kind, text }]);
    window.setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, 4200);
  }, []);

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-5 top-5 z-[100] flex w-[min(360px,90vw)] flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            className="fade-in pointer-events-auto border px-4 py-3 text-[13px] leading-relaxed"
            style={{
              background: '#0e1119',
              borderColor:
                t.kind === 'success'
                  ? 'rgba(83,230,166,.45)'
                  : t.kind === 'error'
                    ? 'rgba(255,157,148,.45)'
                    : 'rgba(150,160,190,.3)',
              color: '#e8eaf2',
            }}
          >
            <span
              className="mr-2 inline-block h-2 w-2 rounded-full align-middle"
              style={{
                background:
                  t.kind === 'success'
                    ? '#53e6a6'
                    : t.kind === 'error'
                      ? '#ff9d94'
                      : '#9aa3bd',
              }}
            />
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/* ---------------- 基础控件 ---------------- */

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'ghost' | 'danger' | 'outline';
  loading?: boolean;
};

export function Button({
  variant = 'outline',
  loading,
  className = '',
  disabled,
  children,
  ...rest
}: ButtonProps) {
  const styles =
    variant === 'primary'
      ? 'border-[rgba(83,230,166,.55)] bg-[rgba(83,230,166,.12)] text-[#e8eaf2] hover:bg-[rgba(83,230,166,.2)]'
      : variant === 'danger'
        ? 'border-[rgba(255,157,148,.55)] bg-[rgba(255,157,148,.08)] text-[#ff9d94] hover:bg-[rgba(255,157,148,.16)]'
        : variant === 'ghost'
          ? 'border-transparent text-[#9aa3bd] hover:text-[#e8eaf2] hover:bg-[rgba(150,160,190,.08)]'
          : 'border-hair bg-[rgba(150,160,190,.05)] text-[#e8eaf2] hover:border-hair-2 hover:bg-[rgba(150,160,190,.1)]';
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 border px-4 py-2 font-mono text-[11px] tracking-[0.18em] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${styles} ${className}`}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Spinner size={12} />}
      {children}
    </button>
  );
}

export function Spinner({ size = 14 }: { size?: number }) {
  return (
    <span
      className="inline-block animate-spin rounded-full border border-current border-t-transparent"
      style={{ width: size, height: size }}
    />
  );
}

const inputCls =
  'w-full border border-hair bg-[rgba(150,160,190,.04)] px-3 py-2 text-[13px] text-ink placeholder:text-faint outline-none transition-colors focus:border-hair-2 focus:bg-[rgba(150,160,190,.07)]';

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputCls} ${props.className ?? ''}`} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea {...props} className={`${inputCls} min-h-[76px] resize-y ${props.className ?? ''}`} />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${inputCls} ${props.className ?? ''}`} />;
}

export function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1.5 block font-mono text-[10px] tracking-[0.24em] text-faint">
        {label}
        {required && <span className="ml-1 text-danger">*</span>}
      </label>
      {children}
      {hint && <p className="mt-1 text-[11px] leading-relaxed text-faint">{hint}</p>}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="inline-flex items-center gap-2.5"
      role="switch"
      aria-checked={checked}
    >
      <span
        className="relative inline-block h-[20px] w-[36px] shrink-0 rounded-full border transition-colors"
        style={{
          borderColor: checked ? 'rgba(83,230,166,.6)' : 'rgba(150,160,190,.3)',
          background: checked ? 'rgba(83,230,166,.25)' : 'rgba(150,160,190,.08)',
        }}
      >
        <span
          className="absolute top-1/2 h-[12px] w-[12px] -translate-y-1/2 rounded-full transition-all"
          style={{
            left: checked ? '20px' : '4px',
            background: checked ? '#53e6a6' : '#9aa3bd',
          }}
        />
      </span>
      {label && <span className="text-[13px] text-mute">{label}</span>}
    </button>
  );
}

/* ---------------- 弹窗 ---------------- */

export function Modal({
  title,
  sub,
  onClose,
  children,
  wide,
}: {
  title: string;
  sub?: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const fn = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', fn);
    return () => window.removeEventListener('keydown', fn);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-[rgba(2,3,6,.7)] backdrop-blur-[2px]"
      />
      <div
        className={`fade-in relative flex max-h-[88vh] flex-col border border-hair bg-panel shadow-[0_40px_120px_-30px_rgba(0,0,0,.9)] ${
          wide ? 'w-[min(960px,100%)]' : 'w-[min(560px,100%)]'
        }`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-hair px-6 py-4">
          <div>
            <h3 className="text-[17px] font-medium text-ink">{title}</h3>
            {sub && (
              <p className="mt-1 font-mono text-[10px] tracking-[0.2em] text-faint">{sub}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="grid h-8 w-8 shrink-0 place-items-center border border-hair text-mute transition-colors hover:border-hair-2 hover:text-ink"
            aria-label="关闭"
          >
            ✕
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmModal({
  title,
  message,
  confirmText = '确认删除',
  onConfirm,
  onClose,
  loading,
}: {
  title: string;
  message: string;
  confirmText?: string;
  onConfirm: () => void;
  onClose: () => void;
  loading?: boolean;
}) {
  return (
    <Modal title={title} onClose={onClose}>
      <p className="text-[13px] leading-relaxed text-mute">{message}</p>
      <div className="mt-6 flex justify-end gap-3">
        <Button onClick={onClose}>取消</Button>
        <Button variant="danger" loading={loading} onClick={onConfirm}>
          {confirmText}
        </Button>
      </div>
    </Modal>
  );
}

/* ---------------- 展示组件 ---------------- */

export function Card({
  title,
  extra,
  children,
  className = '',
}: {
  title?: string;
  extra?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`border border-hair bg-panel ${className}`}>
      {(title || extra) && (
        <div className="flex items-center justify-between gap-3 border-b border-hair px-5 py-3">
          <h3 className="font-mono text-[11px] tracking-[0.24em] text-mute">{title}</h3>
          {extra}
        </div>
      )}
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}

export function Badge({
  tone = 'mute',
  children,
}: {
  tone?: 'success' | 'danger' | 'warn' | 'info' | 'mute';
  children: React.ReactNode;
}) {
  const color =
    tone === 'success'
      ? '#53e6a6'
      : tone === 'danger'
        ? '#ff9d94'
        : tone === 'warn'
          ? '#ffd76a'
          : tone === 'info'
            ? '#6fb3ff'
            : '#9aa3bd';
  return (
    <span
      className="inline-flex items-center gap-1.5 whitespace-nowrap border px-2 py-0.5 font-mono text-[10px] tracking-[0.08em]"
      style={{ borderColor: `${color}55`, color, background: `${color}14` }}
    >
      {children}
    </span>
  );
}

export function PageHeader({
  title,
  desc,
  actions,
}: {
  title: string;
  desc?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 className="text-[22px] font-light tracking-tight text-ink">{title}</h2>
        {desc && <p className="mt-1 text-[13px] text-mute">{desc}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ text = '暂无数据' }: { text?: string }) {
  return (
    <div className="border border-dashed border-hair px-6 py-10 text-center font-mono text-[11px] tracking-[0.2em] text-faint">
      {text}
    </div>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="mt-4 flex items-center justify-between">
      <span className="font-mono text-[11px] tracking-[0.12em] text-faint">
        共 {total} 条 · 第 {page} / {pages} 页
      </span>
      <div className="flex gap-2">
        <Button disabled={page <= 1} onClick={() => onChange(page - 1)}>
          上一页
        </Button>
        <Button disabled={page >= pages} onClick={() => onChange(page + 1)}>
          下一页
        </Button>
      </div>
    </div>
  );
}

export function TableShell({
  head,
  children,
}: {
  head: React.ReactNode[];
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-x-auto border border-hair">
      <table className="w-full border-collapse text-left text-[13px]">
        <thead>
          <tr className="border-b border-hair bg-[rgba(150,160,190,.04)]">
            {head.map((h, i) => (
              <th
                key={i}
                className="whitespace-nowrap px-4 py-2.5 font-mono text-[10px] font-normal tracking-[0.2em] text-faint"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

/* ---------------- 时间格式化 ---------------- */

export function fmtDateTime(s: string | null | undefined): string {
  if (!s) return '—';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function fmtDate(s: string | null | undefined): string {
  if (!s) return '—';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/* ---------------- 轮询 Hook ---------------- */

export function usePolling(
  active: boolean,
  intervalMs: number,
  fn: () => void | Promise<void>,
) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => {
      void ref.current();
    }, intervalMs);
    return () => window.clearInterval(t);
  }, [active, intervalMs]);
}
