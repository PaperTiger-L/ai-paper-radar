import { useEffect, useState } from 'react';
import { api, errorMessage } from '../api';
import type { SmtpConfig } from '../types';
import {
  Badge,
  Button,
  Card,
  Field,
  Input,
  PageHeader,
  Spinner,
  Toggle,
  useToast,
} from '../ui';

export default function SmtpConfigPage() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [hasPassword, setHasPassword] = useState(false);

  const [host, setHost] = useState('');
  const [port, setPort] = useState(465);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fromEmail, setFromEmail] = useState('');
  const [fromName, setFromName] = useState('AI Paper Radar');
  const [useTls, setUseTls] = useState(false);
  const [useSsl, setUseSsl] = useState(true);
  const [testTo, setTestTo] = useState('');

  useEffect(() => {
    api
      .get<SmtpConfig>('/config/smtp')
      .then((c) => {
        setHost(c.host || '');
        setPort(c.port || 465);
        setUsername(c.username || '');
        setFromEmail(c.from_email || '');
        setFromName(c.from_name || 'AI Paper Radar');
        setUseTls(!!c.use_tls);
        setUseSsl(!!c.use_ssl);
        setHasPassword(!!c.has_password);
      })
      .catch((e) => toast('error', errorMessage(e)))
      .finally(() => setLoading(false));
  }, [toast]);

  const save = async () => {
    if (!host.trim() || !fromEmail.trim()) {
      toast('error', '请填写 SMTP 服务器和发件人邮箱');
      return;
    }
    if (!hasPassword && !password.trim()) {
      toast('error', '请填写 SMTP 密码或授权码');
      return;
    }
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        host: host.trim(),
        port: Number(port) || 465,
        username: username.trim(),
        from_email: fromEmail.trim(),
        from_name: fromName.trim(),
        use_tls: useTls,
        use_ssl: useSsl,
      };
      if (password.trim()) payload.password = password.trim();
      const c = await api.put<SmtpConfig>('/config/smtp', payload);
      setHasPassword(!!c.has_password);
      setPassword('');
      toast('success', 'SMTP 配置已保存');
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    if (!testTo.trim()) {
      toast('error', '请先输入测试收件邮箱');
      return;
    }
    setTesting(true);
    try {
      const r = await api.post<{ ok: boolean; message: string }>('/config/smtp/test', {
        to: testTo.trim(),
      });
      toast(r.ok ? 'success' : 'error', r.message || (r.ok ? '测试邮件已发送' : '发送失败'));
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center gap-3 text-mute">
        <Spinner /> 加载中…
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="邮箱配置" desc="配置 SMTP 服务，用于发送每周论文周报" />

      <Card
        title="SMTP 服务"
        extra={hasPassword ? <Badge tone="success">密码已配置</Badge> : <Badge>未配置</Badge>}
        className="max-w-[720px]"
      >
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="SMTP 服务器" required>
            <Input value={host} onChange={(e) => setHost(e.target.value)} placeholder="smtp.example.com" />
          </Field>
          <Field label="端口" required>
            <Input type="number" value={port} onChange={(e) => setPort(Number(e.target.value))} placeholder="465" />
          </Field>
          <Field label="用户名">
            <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="通常为发件人邮箱" />
          </Field>
          <Field
            label="密码 / 授权码"
            required={!hasPassword}
            hint={hasPassword ? '已配置。更换请直接输入新密码；留空不修改。' : 'QQ/163 等邮箱请使用授权码'}
          >
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={hasPassword ? '••••••••（已配置，留空不修改）' : '请输入密码或授权码'}
            />
          </Field>
          <Field label="发件人邮箱" required>
            <Input type="email" value={fromEmail} onChange={(e) => setFromEmail(e.target.value)} placeholder="radar@example.com" />
          </Field>
          <Field label="发件人名称">
            <Input value={fromName} onChange={(e) => setFromName(e.target.value)} placeholder="AI Paper Radar" />
          </Field>
          <div className="flex items-center gap-6 md:col-span-2">
            <Toggle checked={useSsl} onChange={setUseSsl} label="SSL（465）" />
            <Toggle checked={useTls} onChange={setUseTls} label="TLS / STARTTLS（587）" />
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button variant="primary" loading={saving} onClick={save}>
            保存配置
          </Button>
        </div>
      </Card>

      <Card title="发送测试邮件" className="mt-4 max-w-[720px]">
        <div className="flex flex-col gap-3">
          <Field label="测试收件邮箱">
            <div className="flex gap-2">
              <Input
                type="email"
                value={testTo}
                onChange={(e) => setTestTo(e.target.value)}
                placeholder="test@example.com"
              />
              <Button loading={testing} onClick={test} className="shrink-0">
                发送测试
              </Button>
            </div>
          </Field>
          <p className="text-[12px] leading-relaxed text-faint">
            测试邮件用于验证 SMTP 配置是否可用，实际周报内容请在「定时任务」或「论文管理」中使用周报预览功能。
          </p>
        </div>
      </Card>
    </div>
  );
}
