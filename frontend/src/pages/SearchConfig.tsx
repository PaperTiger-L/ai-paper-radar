import { useEffect, useState } from 'react';
import { api, errorMessage } from '../api';
import type { SearchConfig } from '../types';
import {
  Badge,
  Button,
  Card,
  Field,
  Input,
  PageHeader,
  Spinner,
  useToast,
} from '../ui';

const SOURCE_LABEL: Record<string, string> = {
  ui: '网页配置',
  env: '环境变量',
};

export default function SearchConfigPage() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string; latency_ms?: number } | null>(null);
  const [hasKey, setHasKey] = useState(false);
  const [keyPreview, setKeyPreview] = useState('');
  const [source, setSource] = useState('');
  const [apiKey, setApiKey] = useState('');

  const load = async () => {
    try {
      const c = await api.get<SearchConfig>('/config/search');
      setHasKey(!!c.has_api_key);
      setKeyPreview(c.api_key_preview || '');
      setSource(c.source || '');
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const apply = (c: SearchConfig) => {
    setHasKey(!!c.has_api_key);
    setKeyPreview(c.api_key_preview || '');
    setSource(c.source || '');
    setApiKey('');
    setTestResult(null);
  };

  const save = async () => {
    if (!apiKey.trim()) {
      toast('error', '请填写 API Key');
      return;
    }
    setSaving(true);
    try {
      const c = await api.put<SearchConfig>('/config/search', { api_key: apiKey.trim() });
      apply(c);
      toast('success', 'AnySearch Key 已保存');
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await api.post<{ ok: boolean; message: string; latency_ms?: number }>(
        '/config/search/test',
      );
      setTestResult(r);
      toast(r.ok ? 'success' : 'error', r.message || (r.ok ? '连接成功' : '连接失败'));
    } catch (e) {
      const msg = errorMessage(e);
      setTestResult({ ok: false, message: msg });
      toast('error', msg);
    } finally {
      setTesting(false);
    }
  };

  const clear = async () => {
    if (!window.confirm('确定清除网页配置的 Key 吗？清除后将回退到环境变量 ANYSEARCH_API_KEY。')) {
      return;
    }
    setClearing(true);
    try {
      const c = await api.del<SearchConfig>('/config/search/key');
      apply(c);
      toast('success', '已清除，改用环境变量');
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setClearing(false);
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
      <PageHeader title="检索配置" desc="配置论文检索用的 AnySearch API Key" />

      <Card
        title="AnySearch"
        extra={hasKey ? <Badge tone="success">API KEY 已配置</Badge> : <Badge>未配置 KEY</Badge>}
        className="max-w-[720px]"
      >
        <div className="flex flex-col gap-4">
          <Field
            label="API Key"
            hint={
              hasKey
                ? `已配置（${keyPreview}，来源：${SOURCE_LABEL[source] || source}）。如需更换请直接输入新 Key。`
                : '在 https://anysearch.com/console/api-keys 免费注册获取；仅保存在服务器本地，不会出现在日志中'
            }
          >
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={hasKey ? `${keyPreview}（已配置，输入新 Key 更换）` : 'as_sk_…'}
            />
          </Field>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Button variant="primary" loading={saving} onClick={save}>
              保存配置
            </Button>
            <Button loading={testing} onClick={test} disabled={!hasKey}>
              测试连接
            </Button>
            {source === 'ui' && (
              <Button loading={clearing} onClick={clear}>
                清除 Key（改用环境变量）
              </Button>
            )}
            {testResult && (
              <span className="font-mono text-[12px]" style={{ color: testResult.ok ? '#53e6a6' : '#ff9d94' }}>
                {testResult.ok ? '✓' : '✕'} {testResult.message}
                {typeof testResult.latency_ms === 'number' && ` · ${testResult.latency_ms}ms`}
              </span>
            )}
          </div>

          <div className="border-t border-hair pt-3 text-[12px] leading-relaxed text-faint">
            论文检索走 AnySearch 学术双通道（academic.search 跨学科论文 +
            academic.preprint 预印本）。Key 优先级：网页配置 &gt; 环境变量
            ANYSEARCH_API_KEY；两处都未配置时检索会报错跳过。测试连接会真实检索 1
            条论文，绝不伪造成功。
          </div>
        </div>
      </Card>
    </div>
  );
}
