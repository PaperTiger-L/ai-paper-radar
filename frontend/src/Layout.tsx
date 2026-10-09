import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { api, clearToken, errorMessage } from './api';
import {
  Button,
  Field,
  Input,
  Modal,
  useToast,
} from './ui';

const NAV = [
  { to: '/', label: '总览', end: true },
  { to: '/subscribers', label: '用户管理' },
  { to: '/papers', label: '论文管理' },
  { to: '/llm', label: 'LLM 配置' },
  { to: '/smtp', label: '邮箱配置' },
  { to: '/schedule', label: '定时任务' },
  { to: '/logs', label: '日志管理' },
];

function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (newPassword.length < 8) {
      toast('error', '新密码至少需要 8 位');
      return;
    }
    if (newPassword !== confirm) {
      toast('error', '两次输入的新密码不一致');
      return;
    }
    setLoading(true);
    try {
      await api.post('/auth/change-password', {
        old_password: oldPassword,
        new_password: newPassword,
      });
      toast('success', '密码修改成功');
      onClose();
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="修改密码" onClose={onClose}>
      <div className="flex flex-col gap-4">
        <Field label="当前密码" required>
          <Input
            type="password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
            placeholder="请输入当前密码"
          />
        </Field>
        <Field label="新密码" required hint="至少 8 位">
          <Input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="请输入新密码"
          />
        </Field>
        <Field label="确认新密码" required>
          <Input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="再次输入新密码"
          />
        </Field>
        <div className="flex justify-end gap-3">
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" loading={loading} onClick={submit}>
            保存
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default function Layout() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const [showPwd, setShowPwd] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .get<{ username: string }>('/auth/me')
      .then((r) => setUsername(r.username))
      .catch(() => navigate('/', { replace: true }));
  }, [navigate]);

  useEffect(() => {
    const fn = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', fn);
    return () => document.removeEventListener('mousedown', fn);
  }, []);

  const logout = () => {
    clearToken();
    window.location.href = '/';
  };

  return (
    <div className="flex h-full">
      {/* 侧边栏 */}
      <aside className="flex w-[212px] shrink-0 flex-col border-r border-hair bg-panel">
        <div className="border-b border-hair px-5 py-5">
          <div className="font-mono text-[11px] tracking-[0.3em] text-ink">
            AI PAPER RADAR
          </div>
          <div className="mt-1.5 font-mono text-[9px] tracking-[0.24em] text-faint">
            智能论文雷达 · 管理后台
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto p-3">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `mb-1 block border px-4 py-2.5 text-[13px] transition-colors ${
                  isActive
                    ? 'border-hair-2 bg-[rgba(150,160,190,.1)] text-ink'
                    : 'border-transparent text-mute hover:bg-[rgba(150,160,190,.05)] hover:text-ink'
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-hair px-5 py-4 font-mono text-[9px] tracking-[0.2em] text-faint">
          v0.1.0
        </div>
      </aside>

      {/* 主区域 */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 items-center justify-between border-b border-hair bg-panel px-6 py-3">
          <div className="font-mono text-[10px] tracking-[0.24em] text-faint">
            CONSOLE
          </div>
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((v) => !v)}
              className="flex items-center gap-2.5 border border-hair bg-[rgba(150,160,190,.05)] px-3.5 py-1.5 text-[13px] text-ink transition-colors hover:border-hair-2"
            >
              <span className="grid h-6 w-6 place-items-center rounded-full bg-[rgba(83,230,166,.15)] font-mono text-[11px] text-success">
                {(username || '?').slice(0, 1).toUpperCase()}
              </span>
              <span className="max-w-[120px] truncate">{username || '…'}</span>
              <span className="text-[10px] text-faint">▾</span>
            </button>
            {menuOpen && (
              <div className="fade-in absolute right-0 top-full z-50 mt-2 w-44 border border-hair bg-panel-2 shadow-[0_20px_60px_rgba(0,0,0,.6)]">
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    setShowPwd(true);
                  }}
                  className="block w-full px-4 py-2.5 text-left text-[13px] text-mute transition-colors hover:bg-[rgba(150,160,190,.08)] hover:text-ink"
                >
                  修改密码
                </button>
                <button
                  onClick={logout}
                  className="block w-full border-t border-hair px-4 py-2.5 text-left text-[13px] text-danger transition-colors hover:bg-[rgba(255,157,148,.08)]"
                >
                  退出登录
                </button>
              </div>
            )}
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1180px] px-6 py-7">
            <Outlet />
          </div>
        </main>
      </div>

      {showPwd && <ChangePasswordModal onClose={() => setShowPwd(false)} />}
    </div>
  );
}
