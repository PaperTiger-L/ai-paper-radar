import { useEffect, useRef, useState } from 'react';
import { api, errorMessage } from '../api';
import type { LlmConfig } from '../types';
import {
  Badge,
  Button,
  Card,
  Field,
  Input,
  PageHeader,
  Select,
  Spinner,
  useToast,
} from '../ui';

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI', base: 'https://api.openai.com/v1' },
  { value: 'deepseek', label: 'DeepSeek', base: 'https://api.deepseek.com/v1' },
  { value: 'qwen', label: 'Qwen（通义千问）', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { value: 'gemini', label: 'Gemini', base: 'https://generativelanguage.googleapis.com/v1beta/openai' },
  { value: 'custom', label: '自定义（OpenAI 兼容）', base: '' },
];

export default function LlmConfig() {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string; latency_ms?: number } | null>(null);
  const [hasKey, setHasKey] = useState(false);
  const [keyPreview, setKeyPreview] = useState('');

  const [provider, setProvider] = useState('openai');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [models, setModels] = useState<string[]>([]);
  const [modelsOpen, setModelsOpen] = useState(false);
  const [fetchingModels, setFetchingModels] = useState(false);
  const comboRef = useRef<HTMLDivElement>(null);

  // 点击下拉框外部关闭
  useEffect(() => {
    const fn = (e: MouseEvent) => {
      if (comboRef.current && !comboRef.current.contains(e.target as Node)) {
        setModelsOpen(false);
      }
    };
    document.addEventListener('mousedown', fn);
    return () => document.removeEventListener('mousedown', fn);
  }, []);

  useEffect(() => {
    api
      .get<LlmConfig>('/config/llm')
      .then((c) => {
        setProvider(c.provider || 'openai');
        setBaseUrl(c.base_url || '');
        setModel(c.model || '');
        setHasKey(!!c.has_api_key);
        setKeyPreview(c.api_key_preview || '');
      })
      .catch((e) => toast('error', errorMessage(e)))
      .finally(() => setLoading(false));
  }, [toast]);

  const onProviderChange = (v: string) => {
    setProvider(v);
    const p = PROVIDERS.find((x) => x.value === v);
    if (p && v !== 'custom') setBaseUrl(p.base);
  };

  const save = async () => {
    if (!model.trim()) {
      toast('error', '请填写模型名称');
      return;
    }
    if (!hasKey && !apiKey.trim()) {
      toast('error', '请填写 API Key');
      return;
    }
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        provider,
        base_url: baseUrl.trim(),
        model: model.trim(),
      };
      // 已配置过 Key 且输入框为空时，不覆盖原 Key
      if (apiKey.trim()) payload.api_key = apiKey.trim();
      const c = await api.put<LlmConfig>('/config/llm', payload);
      setHasKey(!!c.has_api_key);
      setKeyPreview(c.api_key_preview || '');
      setApiKey('');
      setTestResult(null);
      toast('success', 'LLM 配置已保存');
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
        '/config/llm/test',
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

  const fetchModels = async () => {
    setFetchingModels(true);
    try {
      // 用表单当前值拉取（免保存）；留空则后端用已保存的配置
      const r = await api.post<{ models: string[] }>('/config/llm/models', {
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
      });
      const list = r.models ?? [];
      setModels(list);
      setModelsOpen(true);
      if (list.length === 0) toast('error', '未获取到模型列表');
      else toast('success', `获取到 ${list.length} 个模型`);
    } catch (e) {
      toast('error', errorMessage(e));
    } finally {
      setFetchingModels(false);
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
      <PageHeader title="LLM 配置" desc="配置用于搜索策略生成、论文筛选与摘要总结的大语言模型" />

      <Card
        title="模型服务"
        extra={hasKey ? <Badge tone="success">API KEY 已配置</Badge> : <Badge>未配置 KEY</Badge>}
        className="max-w-[720px]"
      >
        <div className="flex flex-col gap-4">
          <Field label="服务商">
            <Select value={provider} onChange={(e) => onProviderChange(e.target.value)}>
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="API Base URL" hint="OpenAI 兼容接口地址，如 https://api.openai.com/v1">
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
            />
          </Field>
          <Field
            label="API Key"
            hint={
              hasKey
                ? `已配置（${keyPreview}）。如需更换请直接输入新 Key；留空则保持原 Key 不变。`
                : '仅保存在服务器本地，不会出现在日志中'
            }
          >
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={hasKey ? `${keyPreview}（已配置，留空不修改）` : 'sk-…'}
            />
          </Field>
          <Field
            label="Model Name"
            hint="可手动输入，或点右侧按钮拉取模型列表后选择；在输入框中打字可即时过滤"
          >
            <div ref={comboRef} className="relative">
              <div className="flex gap-2">
                <Input
                  value={model}
                  onChange={(e) => {
                    setModel(e.target.value);
                    if (models.length) setModelsOpen(true);
                  }}
                  onFocus={() => {
                    if (models.length) setModelsOpen(true);
                  }}
                  placeholder="deepseek-chat"
                />
                <Button
                  loading={fetchingModels}
                  onClick={fetchModels}
                  className="shrink-0"
                  title="调用服务商 /models 接口拉取可用模型（用当前表单的 Base URL 和 Key）"
                >
                  获取模型列表
                </Button>
              </div>
              {modelsOpen && models.length > 0 && (
                <div className="absolute inset-x-0 top-full z-50 mt-1 max-h-56 overflow-y-auto border border-hair bg-panel-2 shadow-[0_20px_60px_rgba(0,0,0,.6)]">
                  {models.filter((m) =>
                    m.toLowerCase().includes(model.trim().toLowerCase()),
                  ).length === 0 ? (
                    <div className="px-3 py-2.5 text-[12px] text-faint">无匹配模型</div>
                  ) : (
                    models
                      .filter((m) => m.toLowerCase().includes(model.trim().toLowerCase()))
                      .map((m) => (
                        <button
                          key={m}
                          type="button"
                          onClick={() => {
                            setModel(m);
                            setModelsOpen(false);
                          }}
                          className={`block w-full px-3 py-2 text-left font-mono text-[12px] transition-colors hover:bg-[rgba(150,160,190,.08)] ${
                            m === model.trim() ? 'text-success' : 'text-mute hover:text-ink'
                          }`}
                        >
                          {m}
                        </button>
                      ))
                  )}
                </div>
              )}
            </div>
          </Field>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Button variant="primary" loading={saving} onClick={save}>
              保存配置
            </Button>
            <Button loading={testing} onClick={test}>
              测试连接
            </Button>
            {testResult && (
              <span className="font-mono text-[12px]" style={{ color: testResult.ok ? '#53e6a6' : '#ff9d94' }}>
                {testResult.ok ? '✓' : '✕'} {testResult.message}
                {typeof testResult.latency_ms === 'number' && ` · ${testResult.latency_ms}ms`}
              </span>
            )}
          </div>

          <div className="border-t border-hair pt-3 text-[12px] leading-relaxed text-faint">
            LLM 负责三件事：① 根据用户研究方向生成搜索关键词；② 筛选与研究问题最相关的论文；③
            生成中文摘要、核心创新点与推荐理由。所有论文均来自真实学术数据源，LLM 不编造论文。
          </div>
        </div>
      </Card>
    </div>
  );
}
